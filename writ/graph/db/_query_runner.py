from __future__ import annotations


class _QueryRunnerMixin:
    """Shared open-session / run-one-query / materialize helper for the db store mixins.

    Mirrors writ/graph/integrity/_query.py::_QueryMixin. Reads self._driver /
    self._database (set by Neo4jConnection.__init__) via the MRO.
    """

    async def _run(self, query: str, **params) -> list:
        async with self._driver.session(database=self._database) as session:
            result = await session.run(query, **params)
            return [record async for record in result]

    async def _run_single(self, query: str, **params):
        async with self._driver.session(database=self._database) as session:
            result = await session.run(query, **params)
            return await result.single()
