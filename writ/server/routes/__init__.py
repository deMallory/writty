# writ-auth-scan: internal-service
"""Per-domain FastAPI APIRouter modules for the Writ session daemon.

Each module owns exactly one route domain and is wired into the single `app`
in writ/server/__init__.py via `app.include_router(...)`. Handlers access
mutable/monkeypatched daemon state via live `server.<attr>` attribute access on
the `writ.server` module, never via frozen `from writ.server import <name>`
snapshots (the monkeypatch seam).
"""
