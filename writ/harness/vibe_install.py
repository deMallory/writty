"""Install Writ for Mistral Vibe into a Vibe home of its own (default ~/.mistty).

`bin/mistty` starts Vibe with VIBE_HOME pointing at that home, so Writ's hooks govern
those sessions only. Plain `vibe` and ~/.vibe stay ungoverned for non-coding use. The
home shares `.env` and `config.toml` with ~/.vibe by symlink and nothing else.

Every conflict is found before the first write, so a refused install leaves no trace.
Run it through scripts/bootstrap-vibe.sh. Stdlib-only, like the bridge.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

from writ.harness.vibe import _TOOLS, PLUGIN_ROOT, POST, PRE

HOOK = Path(PLUGIN_ROOT) / "bin" / "writ-vibe-hook"
LAUNCHER = Path(PLUGIN_ROOT) / "bin" / "mistty"
SHARED = (".env", "config.toml")
_OWNED = "writ-"

# Runs under Vibe's own interpreter: the same loader a session uses, in strict mode.
_LOAD = (
    "import json, sys\n"
    "from pathlib import Path\n"
    "from vibe.core.hooks.config import load_hooks_file\n"
    "r = load_hooks_file(Path(sys.argv[1]), strict=True)\n"
    "print(json.dumps({'issues': [i.message for i in r.issues],"
    " 'names': [h.name for h in r.hooks]}))\n"
)


def matcher() -> str:
    """Exactly the tools the bridge maps. Vibe fullmatches `re:` patterns, ignoring case,
    so a tool the bridge would pass through never pays for starting it."""
    return "re:" + "|".join(re.escape(name) for name in sorted(_TOOLS))


def render_hooks() -> str:
    # json.dumps output is a valid TOML basic string, backslashes included.
    match = json.dumps(matcher())
    out = "# Written by writty's scripts/bootstrap-vibe.sh, which owns every writ-* entry.\n"
    for name, event, strict in (("writ-pre", PRE, True), ("writ-post", POST, False)):
        out += (f'\n[[hooks]]\nname = "{name}"\ntype = "{event}"\nmatch = {match}\n'
                f"command = {json.dumps(f'{shlex.quote(str(HOOK))} {event}')}\n")
        if strict:
            # A bridge that crashes before printing still denies the call.
            out += "strict = true\n"
    return out


def _conflicts(home: Path, bin_dir: Path) -> list[str]:
    found = []
    hooks = home / "hooks.toml"
    if hooks.exists():
        try:
            entries = tomllib.loads(hooks.read_text()).get("hooks", [])
        except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as e:
            found.append(f"{hooks} is unreadable ({e}); move it aside and rerun")
        else:
            names = [e.get("name") if isinstance(e, dict) else None for e in entries]
            foreign = [repr(n) for n in names if not (isinstance(n, str) and n.startswith(_OWNED))]
            if foreign:
                found.append(f"{hooks} holds hooks this installer does not own: "
                             f"{', '.join(foreign)}")
    link = bin_dir / "mistty"
    if (link.exists() or link.is_symlink()) and not _links_to(link, LAUNCHER):
        found.append(f"{link} exists and is not a link to {LAUNCHER}")
    return found


def _links_to(link: Path, target: Path) -> bool:
    return link.is_symlink() and Path(os.readlink(link)) == target


def _share(home: Path, source_home: Path, name: str) -> str:
    src, dst = source_home / name, home / name
    if _links_to(dst, src):
        return f"link {name} -> {src}"
    if dst.exists() or dst.is_symlink():
        return f"keep {name}: already present"
    if not src.exists():
        return f"skip {name}: {src} does not exist"
    dst.symlink_to(src)
    return f"link {name} -> {src}"


def _write_hooks(home: Path) -> str:
    path, text = home / "hooks.toml", render_hooks()
    if path.exists() and path.read_text() == text:
        return "keep hooks.toml: up to date"
    fd, tmp = tempfile.mkstemp(dir=home, prefix=".hooks.toml.")
    with os.fdopen(fd, "w") as f:
        f.write(text)
    os.replace(tmp, path)
    return f"write {path}"


def vibe_python() -> str | None:
    """The interpreter of the `vibe` on PATH, read from its shebang (uv writes an
    absolute path to the tool's venv python)."""
    exe = shutil.which("vibe")
    if not exe:
        return None
    try:
        with open(os.path.realpath(exe), "rb") as f:
            first = f.readline().decode(errors="replace")
    except OSError:
        return None
    parts = first[2:].split() if first.startswith("#!") else []
    return parts[0] if parts and os.access(parts[0], os.X_OK) else None


def _check(path: Path, python: str) -> list[str]:
    try:
        proc = subprocess.run([python, "-c", _LOAD, str(path)],
                              capture_output=True, text=True, timeout=60)
        return [str(i) for i in json.loads(proc.stdout)["issues"]]
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError) as e:
        return [f"Vibe's loader did not run ({e})"]


def main(argv: list[str] | None = None) -> int:
    home_default = os.environ.get("MISTTY_HOME") or str(Path.home() / ".mistty")
    parser = argparse.ArgumentParser(
        prog="bootstrap-vibe.sh",
        description="Install Writ's hooks into a separate Vibe home and link `mistty`.")
    parser.add_argument("--home", default=home_default,
                        help="the mistty Vibe home (default: $MISTTY_HOME or ~/.mistty)")
    parser.add_argument("--source-home", default=str(Path.home() / ".vibe"),
                        help="where .env and config.toml come from (default: ~/.vibe)")
    parser.add_argument("--bin-dir", default=str(Path.home() / ".local" / "bin"),
                        help="where the mistty launcher is linked (default: ~/.local/bin)")
    parser.add_argument("--vibe-python",
                        help="interpreter for the loader check (default: from `vibe` on PATH)")
    parser.add_argument("--no-check", action="store_true",
                        help="skip validating hooks.toml with Vibe's loader")
    args = parser.parse_args(argv)
    home, source_home, bin_dir = (Path(p).expanduser().absolute()
                                  for p in (args.home, args.source_home, args.bin_dir))

    conflicts = _conflicts(home, bin_dir)
    if conflicts:
        for c in conflicts:
            print(f"conflict: {c}")
        print("nothing written")
        return 1

    home.mkdir(mode=0o700, parents=True, exist_ok=True)
    home.chmod(0o700)
    for name in SHARED:
        print(_share(home, source_home, name))
    print(_write_hooks(home))
    bin_dir.mkdir(parents=True, exist_ok=True)
    if not _links_to(bin_dir / "mistty", LAUNCHER):
        (bin_dir / "mistty").symlink_to(LAUNCHER)
    print(f"link {bin_dir / 'mistty'} -> {LAUNCHER}")

    if args.no_check:
        return 0
    python = args.vibe_python or vibe_python()
    if not python:
        print("check hooks.toml: skipped, no vibe on PATH")
        return 0
    issues = _check(home / "hooks.toml", python)
    print(f"check hooks.toml: Vibe's loader reports {len(issues)} issues")
    for issue in issues:
        print(f"  {issue}")
    return 1 if issues else 0


if __name__ == "__main__":
    sys.exit(main())
