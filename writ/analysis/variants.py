"""Declarative variant profiles for efficacy-ab. The experiment is DATA, not code: a new lever
(full-vs-summary, gate-on/off) slots in here without touching the runner."""
from __future__ import annotations

import json
import os

# Both arms run --dangerously-skip-permissions (sandboxed throwaway repo copy) so the ONLY
# difference between arms is the Writ hook stack -- a clean controlled experiment.
NO_HOOKS_SETTINGS = {
    "disableAllHooks": True,
    "permissions": {"allow": ["Bash", "Read", "Write", "Edit", "Glob", "Grep"]},
}

VARIANTS = {
    "writ-on":  {"env": {}, "hooks": True},                          # live daemon, hooks fire
    "writ-off": {"env": {"WRIT_NO_AUTOSTART": "1"}, "hooks": False},  # disableAllHooks via --settings
}


def materialize_variant(name: str, cache_root: str) -> dict:
    """Produce the concrete run profile: isolated WRIT_CACHE_DIR + per-run WRIT_FRICTION_LOG (so we
    can read THIS run's gate events), and a generated no-hooks.json for the writ-off arm."""
    if name not in VARIANTS:
        raise KeyError(f"unknown variant {name!r}; known: {sorted(VARIANTS)}")
    base = VARIANTS[name]
    cache_dir = os.path.join(cache_root, name)
    os.makedirs(cache_dir, exist_ok=True)
    friction = os.path.join(cache_dir, "friction.log")
    env = dict(base["env"])
    env["WRIT_CACHE_DIR"] = cache_dir
    env["WRIT_FRICTION_LOG"] = friction
    settings_file = None
    if not base["hooks"]:
        settings_file = os.path.join(cache_dir, "no-hooks.json")
        with open(settings_file, "w") as fh:
            json.dump(NO_HOOKS_SETTINGS, fh)
    return {"name": name, "env": env, "settings_file": settings_file, "friction_log": friction}
