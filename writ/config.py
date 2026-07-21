"""Centralized writ.toml loader using tomllib (Python 3.11+).

Returns typed config dict. All modules read config through this, not hardcoded values.

Per ARCH-CONST-001: all tunables must live in writ.toml with named constant defaults.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore[no-redef]

# Per ARCH-CONST-001: named constants for defaults.
DEFAULT_NEO4J_URI = "bolt://localhost:7687"
DEFAULT_NEO4J_USER = "neo4j"
DEFAULT_NEO4J_PASSWORD = "writdevpass"
DEFAULT_HNSW_CACHE_DIR = str(Path.home() / ".cache" / "writ" / "hnsw")

# Default config file path: writ.toml in the package root (one level above writ/).
_PACKAGE_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_CONFIG_PATH = str(_PACKAGE_ROOT / "writ.toml")


def _warn_config_ignored(config_path: str, reason: str) -> None:
    """Emit the single stderr warning shared by load_config's two failure branches.

    A malformed/unparseable writ.toml and an unreadable one both fall back to
    built-in defaults; both must say so visibly (never silently swallow). DRY: one
    helper owns the "writ: warning: config file <path> <reason>; falling back to
    built-in defaults" boilerplate so the two except branches cannot drift.
    """
    print(
        f"writ: warning: config file {config_path} {reason}; "
        f"falling back to built-in defaults",
        file=sys.stderr,
    )


def load_config(path: str | None = None) -> dict[str, Any]:
    """Load and return the parsed writ.toml as a dict.

    Returns an empty dict when the file does not exist or is empty.
    """
    config_path = path if path is not None else _DEFAULT_CONFIG_PATH
    if not os.path.isfile(config_path):
        return {}
    try:
        with open(config_path, "rb") as f:
            data = tomllib.load(f)
        return data if data else {}
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as e:
        _warn_config_ignored(
            config_path, f"is malformed (unparseable) and was ignored ({e})"
        )
        return {}
    except OSError as e:
        _warn_config_ignored(config_path, f"could not be read ({e})")
        return {}


def get_neo4j_uri(path: str | None = None) -> str:
    """Return neo4j.uri from config, falling back to DEFAULT_NEO4J_URI."""
    cfg = load_config(path)
    return cfg.get("neo4j", {}).get("uri", DEFAULT_NEO4J_URI)


def get_neo4j_user(path: str | None = None) -> str:
    """Return neo4j.user from config, falling back to DEFAULT_NEO4J_USER."""
    cfg = load_config(path)
    return cfg.get("neo4j", {}).get("user", DEFAULT_NEO4J_USER)


def get_neo4j_password(path: str | None = None) -> str:
    """Return neo4j.password from config, falling back to DEFAULT_NEO4J_PASSWORD."""
    cfg = load_config(path)
    return cfg.get("neo4j", {}).get("password", DEFAULT_NEO4J_PASSWORD)


def get_bitbucket_email(path: str | None = None) -> str | None:
    """Return the Bitbucket account email from writ.toml [bitbucket].email.

    writ.toml is gitignored (see writ.toml.example) so the credential never lands
    in a tracked file. Mirrors get_neo4j_password (also toml-sourced, no env).
    Returns None when the section or value is absent.
    """
    cfg = load_config(path)
    return cfg.get("bitbucket", {}).get("email") or None


def get_bitbucket_token(path: str | None = None) -> str | None:
    """Return the Bitbucket API token from writ.toml [bitbucket].token.

    writ.toml is gitignored (see writ.toml.example) so the token never lands in a
    tracked file. The token is never logged. Returns None when the section or
    value is absent.
    """
    cfg = load_config(path)
    return cfg.get("bitbucket", {}).get("token") or None


def get_hnsw_cache_dir(path: str | None = None) -> str:
    """Return hnsw.cache_dir from config, falling back to DEFAULT_HNSW_CACHE_DIR.

    TOML strings like "~/.cache/writ/hnsw" are expanded to an absolute path.
    Without this, Path() treats "~" as a literal dir name and creates a
    stray "~" folder wherever the process runs.
    """
    cfg = load_config(path)
    raw = cfg.get("hnsw", {}).get("cache_dir", DEFAULT_HNSW_CACHE_DIR)
    return os.path.expanduser(raw)


def get_logs_backup_dest(path: str | None = None) -> str | None:
    """Return the logs backup destination from writ.toml [logs].backup_dest.

    A leading ~ is expanded (os.path.expanduser), mirroring get_hnsw_cache_dir,
    so a configured "~/writ-backups" resolves to an absolute path rather than a
    stray "~" directory. Returns None when the section or value is absent
    (mirrors get_bitbucket_email); there is no meaningful default destination,
    so `writ logs backup` requires an explicit --dest or a configured value.
    """
    cfg = load_config(path)
    raw = cfg.get("logs", {}).get("backup_dest")
    if not raw:
        return None
    return os.path.expanduser(raw)
