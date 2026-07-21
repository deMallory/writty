"""BitbucketClient: the PrHost adapter for the Bitbucket Cloud REST API (Phase 1e).

One narrow adapter (ARCH-BOUNDARY-001) implementing the five PrHost methods the
per-PR sync uses: find_open_pr, get_pr_diffstat, create_file_comment,
list_comments, update_comment. The base host is hardcoded
(https://api.bitbucket.org/2.0) and is the only destination the client ever
connects to. Basic auth comes from env-supplied (email, token); the token and the
Authorization header are NEVER logged or printed (error logs carry status code +
endpoint path only). A 429 retries with a bounded exponential backoff and then
surfaces; any other non-2xx raises (FAIL LOUD, no swallowing). Redirects are
followed MANUALLY and only to allowlisted hosts (SEC-INJ-SSRF-001); an
off-allowlist redirect target raises (refuse, never follow).
"""

from __future__ import annotations

import asyncio
import logging
from urllib.parse import urlsplit

import httpx

logger = logging.getLogger(__name__)


class BitbucketClient:
    """PrHost implementation over the Bitbucket Cloud 2.0 REST API."""

    BASE = "https://api.bitbucket.org/2.0"
    # The hosts a redirect Location may point to. api.bitbucket.org is the base
    # host; bitbucket.org covers the diffstat 302 target.
    ALLOWED_HOSTS = frozenset({"bitbucket.org", "api.bitbucket.org"})
    DEFAULT_PAGELEN = 50  # Bitbucket /pullrequests max is 50; safe for all paginated endpoints
    RATELIMIT_MAX_RETRIES = 3
    RATELIMIT_BACKOFF_SECONDS = 2.0
    # Bound on chained redirects so a redirect loop cannot spin forever.
    MAX_REDIRECTS = 5

    def __init__(
        self,
        email: str,
        token: str,
        *,
        http_client: "httpx.AsyncClient | None" = None,
    ) -> None:
        """Build the client with Basic auth = (email, token).

        When http_client is None a fresh httpx.AsyncClient is created with
        auth=(email, token) and follow_redirects=False (redirects are followed
        manually against the host allowlist). An injected http_client (tests) is
        used as-is, never reconfigured to auto-follow redirects. The token and
        email are never logged and the Authorization header is never echoed.
        """
        if http_client is None:
            self._client = httpx.AsyncClient(
                auth=(email, token), follow_redirects=False
            )
            self._owns_client = True
        else:
            self._client = http_client
            self._owns_client = False

    async def close(self) -> None:
        """Close the underlying client when this instance owns it."""
        if self._owns_client:
            await self._client.aclose()

    # --- request core -----------------------------------------------------

    @staticmethod
    def _host_allowed(url: str) -> bool:
        """True when the URL host is on the redirect allowlist."""
        return urlsplit(url).hostname in BitbucketClient.ALLOWED_HOSTS

    async def _request(
        self, method: str, url: str, *, params: dict | None = None, json: dict | None = None
    ) -> httpx.Response:
        """Issue one request with a bounded 429 backoff and manual redirect follow.

        A 429 retries with an exponential backoff up to RATELIMIT_MAX_RETRIES and
        then surfaces (raise_for_status). A 3xx with a Location header is followed
        only when the target host is allowlisted; an off-allowlist target raises.
        Any other non-2xx raises. The endpoint path (never the token, never the
        Authorization header, never the response body) is the only request detail
        in error logs.
        """
        current_url = url
        current_params = params
        redirects = 0

        while True:
            response = await self._send_with_ratelimit(
                method, current_url, params=current_params, json=json
            )

            if response.is_redirect or (300 <= response.status_code < 400):
                location = response.headers.get("Location") or response.headers.get("location")
                if not location:
                    self._raise_for_status(response, current_url)
                if not self._host_allowed(location):
                    raise httpx.RequestError(
                        f"Refusing off-allowlist redirect from {self._endpoint(current_url)} "
                        f"to a non-allowlisted host"
                    )
                redirects += 1
                if redirects > self.MAX_REDIRECTS:
                    raise httpx.RequestError(
                        f"Too many redirects from {self._endpoint(url)}"
                    )
                # The redirect Location is absolute; params already encoded there.
                current_url = location
                current_params = None
                continue

            self._raise_for_status(response, current_url)
            return response

    async def _send_with_ratelimit(
        self, method: str, url: str, *, params: dict | None, json: dict | None
    ) -> httpx.Response:
        """Send one request, retrying a 429 with a bounded exponential backoff."""
        attempt = 0
        while True:
            response = await self._client.request(method, url, params=params, json=json)
            if response.status_code != 429:
                return response
            if attempt >= self.RATELIMIT_MAX_RETRIES:
                # Bounded retries exhausted; surface the 429 to the caller.
                return response
            backoff = self.RATELIMIT_BACKOFF_SECONDS * (2 ** attempt)
            logger.warning(
                "Bitbucket rate limited (429) on %s; retry %d/%d after %.1fs",
                self._endpoint(url), attempt + 1, self.RATELIMIT_MAX_RETRIES, backoff,
            )
            await asyncio.sleep(backoff)
            attempt += 1

    @staticmethod
    def _endpoint(url: str) -> str:
        """Return the path portion of a URL for safe logging (no host, no creds)."""
        return urlsplit(url).path or url

    def _raise_for_status(self, response: httpx.Response, url: str) -> None:
        """Raise on a non-2xx response, logging status + endpoint only."""
        if 200 <= response.status_code < 300:
            return
        logger.error(
            "Bitbucket request failed: status=%d endpoint=%s",
            response.status_code, self._endpoint(url),
        )
        response.raise_for_status()

    async def _paginate(self, url: str, *, params: dict | None = None) -> list[dict]:
        """GET `url`, then follow each paginated `next` URI, collecting `values`."""
        values: list[dict] = []
        next_url: str | None = url
        next_params = params
        while next_url:
            response = await self._request("GET", next_url, params=next_params)
            data = response.json()
            values.extend(data.get("values", []))
            next_url = data.get("next")
            # The `next` URI is absolute and already carries the query string.
            next_params = None
        return values

    # --- PrHost methods ---------------------------------------------------

    async def find_open_pr(
        self, workspace: str, repo_slug: str, source_branch: str
    ) -> int | None:
        """Return the first OPEN PR id whose source branch == source_branch, else None.

        Lists OPEN PRs (the dedicated `state` query param) and matches the source
        branch in Python. The /pullrequests endpoint rejects filtering on
        source.branch.name via q (HTTP 400) and caps pagelen at 50, so this avoids
        both. Follows the paginated next URI.
        """
        url = f"{self.BASE}/repositories/{workspace}/{repo_slug}/pullrequests"
        params = {"state": "OPEN", "pagelen": self.DEFAULT_PAGELEN}
        values = await self._paginate(url, params=params)
        for pr in values:
            source = pr.get("source") or {}
            branch = source.get("branch") or {}
            if branch.get("name") == source_branch:
                pr_id = pr.get("id")
                if pr_id is not None:
                    return int(pr_id)
        return None

    async def get_pr_diffstat(
        self, workspace: str, repo_slug: str, pr_id: int
    ) -> list[dict]:
        """Return the PR diffstat as [{path, status}, ...].

        Follows the 302 to the repo diffstat (manual, allowlist-checked) and the
        paginated next URI. path = new.path when new and new.path are present,
        else old.path; a null old/new is never dereferenced.
        """
        url = (
            f"{self.BASE}/repositories/{workspace}/{repo_slug}"
            f"/pullrequests/{pr_id}/diffstat"
        )
        entries = await self._paginate(url, params={"pagelen": self.DEFAULT_PAGELEN})
        result: list[dict] = []
        for entry in entries:
            new = entry.get("new")
            old = entry.get("old")
            path = None
            if new and new.get("path"):
                path = new["path"]
            elif old and old.get("path"):
                path = old["path"]
            if path is None:
                continue
            result.append({"path": path, "status": entry.get("status")})
        return result

    async def create_file_comment(
        self, workspace: str, repo_slug: str, pr_id: int, path: str, body: str
    ) -> dict:
        """POST one file-level (path-only, NO line) comment and return the created dict."""
        url = (
            f"{self.BASE}/repositories/{workspace}/{repo_slug}"
            f"/pullrequests/{pr_id}/comments"
        )
        payload = {"content": {"raw": body}, "inline": {"path": path}}
        response = await self._request("POST", url, json=payload)
        return response.json()

    async def list_comments(
        self, workspace: str, repo_slug: str, pr_id: int
    ) -> list[dict]:
        """Return all non-deleted PR comment dicts, following paginated next."""
        url = (
            f"{self.BASE}/repositories/{workspace}/{repo_slug}"
            f"/pullrequests/{pr_id}/comments"
        )
        values = await self._paginate(url, params={"pagelen": self.DEFAULT_PAGELEN})
        return [c for c in values if not c.get("deleted")]

    async def update_comment(
        self, workspace: str, repo_slug: str, pr_id: int, comment_id: int, body: str
    ) -> dict:
        """PUT {"content":{"raw":body}} to the comment and return the updated dict."""
        url = (
            f"{self.BASE}/repositories/{workspace}/{repo_slug}"
            f"/pullrequests/{pr_id}/comments/{comment_id}"
        )
        payload = {"content": {"raw": body}}
        response = await self._request("PUT", url, json=payload)
        return response.json()
