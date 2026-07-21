"""Shared test helpers for BitbucketClient adapter tests.

Consolidates the httpx MockTransport scaffolding formerly duplicated across
the decision-memory pr-comments test file (Wave-5 Cycle 5.3b): the
`_SequentialTransport` replay transport, the `_json_response` builder, and a
`make_bb_client` factory that returns a `(client, transport)` pair so callers
keep `transport._seen` access.

No live HTTP ever fires: `_SequentialTransport` replays a fixed queue of
responses and records each request. `BitbucketClient` is imported LAZILY
inside `make_bb_client` so importing this module never forces the
`writ.session.bitbucket_client` import at collection time.
"""

from __future__ import annotations

import httpx


class _SequentialTransport(httpx.MockTransport):
    """httpx MockTransport that replays a fixed list of (request -> response) pairs.

    Each call to handle_async_request pops the next response from the queue.
    Raises AssertionError if more requests arrive than responses were registered.
    """

    def __init__(self, responses: list[httpx.Response]) -> None:
        self._queue = list(responses)
        self._seen: list[httpx.Request] = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:  # type: ignore[override]
        self._seen.append(request)
        if not self._queue:
            raise AssertionError(
                f"Unexpected request #{len(self._seen)}: {request.method} {request.url}"
            )
        return self._queue.pop(0)

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:  # type: ignore[override]
        return self.handle_request(request)


def _json_response(data: dict, status_code: int = 200) -> httpx.Response:
    return httpx.Response(status_code, json=data)


def make_bb_client(
    responses: list[httpx.Response], *, email: str = "u@example.com", token: str = "tok"
):
    """Build a BitbucketClient with a mocked transport and fake credentials.

    Returns a `(client, transport)` pair so callers can assert on
    `transport._seen` after driving the client. Construction issues no HTTP
    request. BitbucketClient is imported lazily to preserve the pr-comments
    file's RED-import discipline.
    """
    from writ.session.bitbucket_client import BitbucketClient

    transport = _SequentialTransport(responses)
    http_client = httpx.AsyncClient(transport=transport)
    client = BitbucketClient(email, token, http_client=http_client)
    return client, transport
