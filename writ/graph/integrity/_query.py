"""Single-read-query session helper shared by the integrity check mixins (Wave 3).

`_QueryMixin` is composed into IntegrityChecker (see __init__.py) so every check method can
call `self._run(query, **params)` instead of hand-rolling the open-session / run-one-query /
drain boilerplate. Only valid for a block that runs a SINGLE read query on its own session;
multi-query blocks keep their explicit `async with` (they intentionally share one session).
"""

from __future__ import annotations


class _QueryMixin:
    """Provides `_run`: open a session, run one read query, return materialized records."""

    async def _run(self, query: str, **params) -> list:
        """Run one read query; return the fully materialized list of neo4j Record objects.

        The records are detached values: indexing `record["field"]` or calling `record.data()`
        after the session closes performs no I/O. `self._driver` / `self._database` are set by
        `IntegrityChecker.__init__`.
        """
        async with self._driver.session(database=self._database) as session:
            result = await session.run(query, **params)
            return [record async for record in result]
