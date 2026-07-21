"""Decision Memory Phase 1e: per-file PR-comment command (`writ pr sync`).

Test skeleton for the capability gate defined in capabilities.md and plan.md.
Every test in this file is RED until the implementer builds the corresponding
feature. Tests fail on ImportError/AttributeError/AssertionError for the
missing modules/methods -- never on a harness error.

Run interpreter: .venv/bin/python -m pytest (has onnxruntime; system python3
errors on embedding imports).

Neo4j-gated tests use the db_clean fixture (scope "test-dm-1e", repo_root
prefix "/tmp/fake-test-1e-repo") and skip when Neo4j is unreachable.

Pure tests (PURE group) and adapter tests (ADAPTER group) run without Neo4j
or live HTTP. httpx.MockTransport is used to intercept BitbucketClient
outbound calls -- no token needed, no live request ever fires.

Orchestration tests use a FakePrHost test-double implementing PrHost so
sync_pr_comments can be tested without httpx.

CLI tests use typer.testing.CliRunner with monkeypatched host/db + env.

ENF-SYS-005 note: get_latest_filechange_per_path and sync_pr_comments with
a real DB (idempotency marker durability) require Neo4j to prove
MERGE semantics and graph state. Mock-only tests of those behaviors would
prove nothing.

Capability map (29 items from capabilities.md):
  [parse-bb-1]    parse_bitbucket_remote derives (workspace, repo_slug) from https + ssh
  [parse-bb-2]    parse_bitbucket_remote returns None for non-bitbucket.org + None/empty
  [find-pr-1]     find_open_pr lists state=OPEN PRs (no source.branch.name q-filter) and matches branch in code
  [find-pr-2]     find_open_pr follows paginated next; returns None when no open PR
  [diffstat-1]    get_pr_diffstat follows 302 redirect, returns changed paths+status
  [diffstat-2]    get_pr_diffstat resolves new.path / old.path; never dereferences null
  [comment-1]     create_file_comment POSTs file-level body (path only, NO line)
  [auth-1]        BitbucketClient uses hardcoded base host + Basic auth, never logs token
  [ssrf-1]        BitbucketClient refuses off-allowlist redirects
  [list-1]        list_comments follows paginated next, returns non-deleted comments
  [update-1]      update_comment PUTs {"content":{"raw":...}} to .../comments/{id}
  [429-1]         BitbucketClient retries 429 with bounded backoff, surfaces after limit
  [err-1]         BitbucketClient raises on non-429 non-2xx (does not swallow)
  [db-latest-1]   get_latest_filechange_per_path returns most-recent reason per path
  [db-latest-2]   get_latest_filechange_per_path returns one entry per path (latest by ts)
  [norm-1]        normalize_path strips "./" and "/" prefix; join works across both forms
  [sync-1]        sync_pr_comments creates exactly ONE file-level comment per path w/ reason
  [sync-2]        sync_pr_comments is idempotent (update not duplicate; unchanged -> no post)
  [sync-3]        sync_pr_comments skips changed path with no captured reason
  [sync-4]        sync_pr_comments renders "No reason recorded" placeholder for empty reason
  [sync-5]        sync_pr_comments includes change_type + governing rule ids in body
  [sync-6]        sync_pr_comments comments deleted file on old.path
  [sync-7]        sync_pr_comments FAILS LOUD on non-429 post/update error, no fallback
  [cli-sync-1]    writ pr sync resolves open PR, runs sync, reports per-path counts
  [cli-sync-2]    writ pr sync --pr-id N targets PR N, skips find_open_pr
  [cli-sync-3]    writ pr sync exits cleanly (no traceback) when writ.toml [bitbucket] creds absent
  [cli-sync-4]    writ pr sync exits cleanly (no traceback) when no open PR for branch
  [pag-1]         find_open_pr / list_comments pagination: 1 page / 1-over / well-over
  [cfg-1]         get_bitbucket_email / get_bitbucket_token read writ.toml [bitbucket] only (no env); None when section/value absent
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import pytest_asyncio

from tests.fixtures.bitbucket import _json_response, make_bb_client
from writ.config import get_neo4j_password, get_neo4j_uri, get_neo4j_user
from writ.graph.db import Neo4jConnection

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_TEST_SCOPE = "test-dm-1e"
_TEST_REPO_ROOT = "/tmp/fake-test-1e-repo"
_WS = "acme-org"
_SLUG = "my-repo"
_BRANCH = "feature/dm-phase-1e"
_PR_ID = 42


# ---------------------------------------------------------------------------
# Factories (TEST-FIXTURE-001: one factory per domain object, minimal fields)
# ---------------------------------------------------------------------------

def _filechange_factory(**overrides: Any) -> dict:
    """Minimal well-formed FileChange kwarg dict for create_filechange."""
    import uuid
    defaults = {
        "change_id": f"FC-1e-{uuid.uuid4().hex[:8]}",
        "project": _TEST_SCOPE,
        "path": "writ/session/pr_comments.py",
        "change_type": "add",
        "reason": "Add PR comment sync logic.",
        "commit_hash": "deadbeef" * 5,
        "ts": "2026-06-26T10:00:00Z",
    }
    return {**defaults, **overrides}


def _bb_pr_page(pr_id: int, next_url: str | None = None, branch: str = _BRANCH) -> dict:
    """Minimal Bitbucket paginated PR list response (includes source.branch.name)."""
    page: dict = {
        "values": [{"id": pr_id, "state": "OPEN", "source": {"branch": {"name": branch}}}]
    }
    if next_url:
        page["next"] = next_url
    return page


def _bb_diffstat_page(entries: list[dict], next_url: str | None = None) -> dict:
    """Minimal Bitbucket paginated diffstat response."""
    page: dict = {"values": entries}
    if next_url:
        page["next"] = next_url
    return page


def _bb_comments_page(comments: list[dict], next_url: str | None = None) -> dict:
    """Minimal Bitbucket paginated comments response."""
    page: dict = {"values": comments}
    if next_url:
        page["next"] = next_url
    return page


def _bb_diffstat_entry(path: str, status: str = "modified") -> dict:
    """One diffstat entry with new.path set."""
    return {"new": {"path": path}, "old": {"path": path}, "status": status}


def _bb_diffstat_entry_deleted(old_path: str) -> dict:
    """Diffstat entry for a deleted file: new is None, old.path is the path."""
    return {"new": None, "old": {"path": old_path}, "status": "removed"}


def _bb_diffstat_entry_added(new_path: str) -> dict:
    """Diffstat entry for a newly added file: old is None."""
    return {"new": {"path": new_path}, "old": None, "status": "added"}


def _bb_comment(comment_id: int, body: str, path: str | None = None, deleted: bool = False) -> dict:
    """Minimal Bitbucket comment dict."""
    c: dict = {
        "id": comment_id,
        "content": {"raw": body},
        "deleted": deleted,
    }
    if path is not None:
        c["inline"] = {"path": path}
    return c


# ---------------------------------------------------------------------------
# BitbucketClient adapter tests use the shared httpx MockTransport helpers
# from tests/fixtures/bitbucket.py: make_bb_client(responses) returns a
# (client, transport) pair backed by _SequentialTransport, so no token is
# ever needed and no live request fires.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Neo4j-gated fixture -- scope "test-dm-1e"
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture()
async def db_clean():
    """Connect to Neo4j, wipe test-dm-1e scope, yield, clean up.

    Skips when Neo4j is unreachable. Uses project='test-dm-1e' so it never
    touches the live 'writ' corpus. Two-pass teardown mirrors the 1c/1d
    pattern in test_decision_memory_capture.py and test_decision_memory_commit.py.
    """
    conn = Neo4jConnection(get_neo4j_uri(), get_neo4j_user(), get_neo4j_password())
    try:
        async with conn._driver.session(database=conn._database) as s:
            await (await s.run("RETURN 1 AS ok")).consume()
    except Exception:
        await conn.close()
        pytest.skip("Neo4j unreachable")

    await _wipe_1e_test_data(conn)
    yield conn
    await _wipe_1e_test_data(conn)
    await conn.close()


async def _wipe_1e_test_data(conn: Neo4jConnection) -> None:
    """Wipe test-dm-1e project scope and related test-seeded nodes."""
    await conn.clear_project(_TEST_SCOPE)
    async with conn._driver.session(database=conn._database) as s:
        await (await s.run(
            "MATCH (p:Project) WHERE p.name STARTS WITH $prefix DETACH DELETE p",
            prefix=_TEST_SCOPE,
        )).consume()
        await (await s.run(
            "MATCH (p:Project) WHERE p.repo_root STARTS WITH $root DETACH DELETE p",
            root=_TEST_REPO_ROOT,
        )).consume()
        await (await s.run(
            "MATCH (fc:FileChange) WHERE fc.project STARTS WITH $prefix DETACH DELETE fc",
            prefix=_TEST_SCOPE,
        )).consume()
        await (await s.run(
            "MATCH (d:Decision) WHERE d.project STARTS WITH $prefix DETACH DELETE d",
            prefix=_TEST_SCOPE,
        )).consume()
        await (await s.run(
            "MATCH (c:Commit) WHERE c.project STARTS WITH $prefix DETACH DELETE c",
            prefix=_TEST_SCOPE,
        )).consume()
        await (await s.run(
            "MATCH (r:Rule) WHERE r.rule_id STARTS WITH 'TEST1E' DETACH DELETE r",
        )).consume()


# ---------------------------------------------------------------------------
# FakePrHost: test double for orchestration tests (no httpx required)
# ---------------------------------------------------------------------------

class FakePrHost:
    """Synchronous FakePrHost implementing the PrHost protocol.

    Holds call logs and configurable responses. Used in sync_pr_comments
    orchestration tests so no httpx transport is needed.
    """

    def __init__(
        self,
        diffstat: list[dict] | None = None,
        existing_comments: list[dict] | None = None,
    ) -> None:
        self._diffstat: list[dict] = diffstat or []
        self._existing_comments: list[dict] = existing_comments or []
        self._next_comment_id = 1000
        # Call logs (path -> list of body strings)
        self.created: list[dict] = []   # {"path": ..., "body": ...}
        self.updated: list[dict] = []   # {"comment_id": ..., "body": ...}
        self.find_open_pr_calls: int = 0
        self.create_error: Exception | None = None

    async def find_open_pr(self, workspace: str, repo_slug: str, source_branch: str) -> int | None:
        self.find_open_pr_calls += 1
        return _PR_ID

    async def get_pr_diffstat(self, workspace: str, repo_slug: str, pr_id: int) -> list[dict]:
        return list(self._diffstat)

    async def create_file_comment(self, workspace: str, repo_slug: str, pr_id: int, path: str, body: str) -> dict:
        if self.create_error is not None:
            raise self.create_error
        cid = self._next_comment_id
        self._next_comment_id += 1
        self.created.append({"path": path, "body": body})
        return {"id": cid, "content": {"raw": body}, "inline": {"path": path}}

    async def list_comments(self, workspace: str, repo_slug: str, pr_id: int) -> list[dict]:
        return list(self._existing_comments)

    async def update_comment(self, workspace: str, repo_slug: str, pr_id: int, comment_id: int, body: str) -> dict:
        self.updated.append({"comment_id": comment_id, "body": body})
        return {"id": comment_id, "content": {"raw": body}}


class FakeDB:
    """Minimal DB fake for sync_pr_comments orchestration tests.

    Holds per-path reasons returned by get_latest_filechange_per_path. After the
    Phase 1f snapshot change, sync reads cited ids from each record's
    cited_rule_ids, NOT from a live get_open_decisions_for_path lookup, so this
    double no longer implements that method (a cited test must put cited_rule_ids
    on the record).
    """

    def __init__(
        self,
        reasons: dict[str, dict] | None = None,
        statements: dict[str, str] | None = None,
    ) -> None:
        # {path -> {reason, change_type, commit_hash, ts, commit_subject,
        #           queried_rule_ids, cited_rule_ids}}
        self._reasons: dict[str, dict] = reasons or {}
        # {rule_id -> statement}
        self._statements: dict[str, str] = statements or {}

    async def get_latest_filechange_per_path(self, project: str, paths: list[str]) -> dict[str, dict]:
        return {p: self._reasons[p] for p in paths if p in self._reasons}

    async def get_rule_statements(self, rule_ids: list[str]) -> dict[str, str]:
        return {rid: self._statements[rid] for rid in rule_ids if rid in self._statements}


# ===========================================================================
# PURE group: parse_bitbucket_remote, normalize_path
# ===========================================================================

class TestParseBitbucketRemote:
    """[parse-bb-1] and [parse-bb-2] -- no Neo4j, no HTTP."""

    def test_https_url_returns_workspace_and_slug(self) -> None:
        # [parse-bb-1]: HTTPS remote https://bitbucket.org/acme/my-repo.git
        # RED: writ/session/remote_parse.py does not exist (ImportError).
        from writ.session.remote_parse import parse_bitbucket_remote

        result = parse_bitbucket_remote("https://bitbucket.org/acme/my-repo.git")
        assert result is not None, "Expected (workspace, repo_slug), got None"
        workspace, slug = result
        assert workspace == "acme", f"Expected workspace='acme', got {workspace!r}"
        assert slug == "my-repo", f"Expected slug='my-repo', got {slug!r}"

    def test_https_url_no_git_suffix_returns_workspace_and_slug(self) -> None:
        # [parse-bb-1]: HTTPS remote without .git suffix still parses.
        from writ.session.remote_parse import parse_bitbucket_remote

        result = parse_bitbucket_remote("https://bitbucket.org/acme/my-repo")
        assert result is not None
        workspace, slug = result
        assert workspace == "acme"
        assert slug == "my-repo"

    def test_ssh_url_returns_workspace_and_slug(self) -> None:
        # [parse-bb-1]: SSH remote git@bitbucket.org:acme/my-repo.git
        # RED: writ/session/remote_parse.py does not exist (ImportError).
        from writ.session.remote_parse import parse_bitbucket_remote

        result = parse_bitbucket_remote("git@bitbucket.org:acme/my-repo.git")
        assert result is not None, "Expected (workspace, repo_slug) from SSH remote, got None"
        workspace, slug = result
        assert workspace == "acme", f"Expected workspace='acme', got {workspace!r}"
        assert slug == "my-repo", f"Expected slug='my-repo', got {slug!r}"

    def test_non_bitbucket_host_returns_none(self) -> None:
        # [parse-bb-2]: host allowlist reject: self-hosted bitbucket server.
        # RED: writ/session/remote_parse.py does not exist (ImportError).
        from writ.session.remote_parse import parse_bitbucket_remote

        result = parse_bitbucket_remote("https://bitbucket.mycompany.com/acme/my-repo.git")
        assert result is None, (
            f"Expected None for non-bitbucket.org host, got {result!r}"
        )

    def test_github_host_returns_none(self) -> None:
        # [parse-bb-2]: github.com is not bitbucket.org.
        from writ.session.remote_parse import parse_bitbucket_remote

        result = parse_bitbucket_remote("https://github.com/acme/my-repo.git")
        assert result is None

    def test_none_remote_returns_none(self) -> None:
        # [parse-bb-2]: None input returns None without raising.
        from writ.session.remote_parse import parse_bitbucket_remote

        result = parse_bitbucket_remote(None)
        assert result is None

    def test_empty_string_remote_returns_none(self) -> None:
        # [parse-bb-2]: empty string returns None without raising.
        from writ.session.remote_parse import parse_bitbucket_remote

        result = parse_bitbucket_remote("")
        assert result is None


class TestNormalizePath:
    """[norm-1] -- no Neo4j, no HTTP."""

    def test_strips_leading_dot_slash(self) -> None:
        # [norm-1]: "./x" normalizes to "x".
        # RED: writ/session/pr_comments.py does not exist (ImportError).
        from writ.session.pr_comments import normalize_path

        assert normalize_path("./writ/foo.py") == "writ/foo.py"

    def test_strips_leading_slash(self) -> None:
        # [norm-1]: "/x" normalizes to "x".
        from writ.session.pr_comments import normalize_path

        assert normalize_path("/writ/foo.py") == "writ/foo.py"

    def test_plain_path_unchanged(self) -> None:
        # [norm-1]: "x/y" with no prefix stays "x/y".
        from writ.session.pr_comments import normalize_path

        assert normalize_path("writ/foo.py") == "writ/foo.py"

    def test_no_case_fold(self) -> None:
        # [norm-1]: no case folding -- "Writ/Foo.py" stays "Writ/Foo.py".
        from writ.session.pr_comments import normalize_path

        assert normalize_path("Writ/Foo.py") == "Writ/Foo.py"

    def test_dot_slash_path_equals_plain_path_after_normalize(self) -> None:
        # [norm-1]: the ./x path joins the "x" FileChange via get_latest_filechange_per_path
        # because both normalize to the same string.
        from writ.session.pr_comments import normalize_path

        assert normalize_path("./writ/session/pr_comments.py") == normalize_path("writ/session/pr_comments.py"), (
            "normalize_path must produce equal strings for './x' and 'x' so the IN-list join matches"
        )

    def test_slash_path_equals_plain_path_after_normalize(self) -> None:
        # [norm-1]: "/x" and "x" normalize to the same string.
        from writ.session.pr_comments import normalize_path

        assert normalize_path("/writ/session/pr_comments.py") == normalize_path("writ/session/pr_comments.py")


# ===========================================================================
# ADAPTER group: BitbucketClient (httpx.MockTransport, no Neo4j)
# ===========================================================================

class TestFindOpenPr:
    """[find-pr-1], [find-pr-2] -- httpx mocked, no Neo4j."""

    @pytest.mark.asyncio
    async def test_find_open_pr_lists_open_and_matches_branch(self) -> None:
        # [find-pr-1]: find_open_pr lists OPEN PRs (state filter, NO q=source.branch.name,
        # which causes a 400) and matches the source branch in code, returning the id.

        page = _bb_pr_page(pr_id=_PR_ID, branch=_BRANCH)
        client, transport = make_bb_client([_json_response(page)])

        result = await client.find_open_pr(_WS, _SLUG, _BRANCH)
        assert result == _PR_ID, f"Expected pr id {_PR_ID}, got {result!r}"

        url_str = str(transport._seen[0].url)
        assert "source.branch.name" not in url_str, (
            f"must NOT filter on source.branch.name (causes 400); URL was: {url_str}"
        )
        assert "OPEN" in url_str, f"must request state=OPEN; URL was: {url_str}"

    @pytest.mark.asyncio
    async def test_find_open_pr_returns_none_when_branch_differs(self) -> None:
        # [find-pr-1]: an OPEN PR on a DIFFERENT branch yields None (in-code match rejects it).

        page = _bb_pr_page(pr_id=123, branch="some-other-branch")
        client, transport = make_bb_client([_json_response(page)])

        result = await client.find_open_pr(_WS, _SLUG, _BRANCH)
        assert result is None, f"Expected None when no PR matches the branch, got {result!r}"

    @pytest.mark.asyncio
    async def test_find_open_pr_follows_paginated_next(self) -> None:
        # [find-pr-2]: find_open_pr follows the paginated `next` URI and finds a PR
        # on page 2 when page 1 contains no matching PR.
        # RED: writ/session/bitbucket_client.py does not exist (ImportError).

        page1 = {"values": [], "next": "https://api.bitbucket.org/2.0/repositories/acme/repo/pullrequests?page=2"}
        page2 = _bb_pr_page(pr_id=99)
        client, transport = make_bb_client([_json_response(page1), _json_response(page2)])

        result = await client.find_open_pr(_WS, _SLUG, _BRANCH)
        assert result == 99, f"Expected PR id 99 from page 2, got {result!r}"
        assert len(transport._seen) == 2, (
            f"Expected exactly 2 HTTP requests (page 1 + page 2), saw {len(transport._seen)}"
        )

    @pytest.mark.asyncio
    async def test_find_open_pr_returns_none_when_no_open_pr(self) -> None:
        # [find-pr-2]: find_open_pr returns None when no open PR exists.
        # RED: writ/session/bitbucket_client.py does not exist (ImportError).

        empty_page = {"values": []}
        client, transport = make_bb_client([_json_response(empty_page)])

        result = await client.find_open_pr(_WS, _SLUG, "no-such-branch")
        assert result is None, f"Expected None when no PR exists, got {result!r}"


class TestGetPrDiffstat:
    """[diffstat-1], [diffstat-2] -- httpx mocked, no Neo4j."""

    @pytest.mark.asyncio
    async def test_diffstat_follows_302_and_returns_paths(self) -> None:
        # [diffstat-1]: get_pr_diffstat follows the 302 redirect and returns changed
        # paths with status.
        # RED: writ/session/bitbucket_client.py does not exist (ImportError).
        #
        # The client handles redirects MANUALLY (not via httpx follow_redirects=True):
        # it inspects the 302 Location header, checks it against the {bitbucket.org}
        # allowlist, follows the on-allowlist target (issues a second request), and
        # raises on an off-allowlist target. This is the same mechanism that
        # test_client_refuses_off_allowlist_redirect depends on.
        #
        # This test replays a real on-allowlist 302 -> page sequence so that an
        # implementer who skips redirect handling (returns early on a 302) will get
        # an empty/wrong result and the test fails. An implementer who uses httpx
        # follow_redirects=True on a non-302-aware transport will also fail here
        # because _SequentialTransport.handle_request is synchronous and httpx's
        # internal redirect follower may or may not invoke handle_async_request again
        # -- the two-item queue makes the expectation explicit and unambiguous.

        redirect_302 = httpx.Response(
            302,
            headers={"Location": f"https://api.bitbucket.org/2.0/repositories/{_WS}/{_SLUG}/diffstat/1234"},
        )
        entry = _bb_diffstat_entry("writ/session/pr_comments.py", "modified")
        diffstat_page = _bb_diffstat_page([entry])
        client, transport = make_bb_client([redirect_302, _json_response(diffstat_page)])

        result = await client.get_pr_diffstat(_WS, _SLUG, _PR_ID)
        assert isinstance(result, list), f"Expected list, got {type(result)}"
        assert len(result) == 1, f"Expected 1 diffstat entry, got {len(result)}"
        assert result[0]["path"] == "writ/session/pr_comments.py"
        assert result[0]["status"] == "modified"
        # Both requests must have fired: the initial GET and the followed redirect.
        assert len(transport._seen) == 2, (
            f"Client must issue 2 requests (initial + redirect follow); "
            f"saw {len(transport._seen)}"
        )

    @pytest.mark.asyncio
    async def test_diffstat_resolves_new_path_for_add(self) -> None:
        # [diffstat-2]: added file: new.path is used; old is None.
        # RED: writ/session/bitbucket_client.py does not exist (ImportError).

        entry = _bb_diffstat_entry_added("writ/session/new_file.py")
        diffstat_page = _bb_diffstat_page([entry])
        client, transport = make_bb_client([_json_response(diffstat_page)])

        result = await client.get_pr_diffstat(_WS, _SLUG, _PR_ID)
        assert result[0]["path"] == "writ/session/new_file.py", (
            "Added file must resolve path from new.path (old is None)"
        )

    @pytest.mark.asyncio
    async def test_diffstat_falls_back_to_old_path_for_delete(self) -> None:
        # [diffstat-2]: deleted file: new is None; old.path is used.
        # RED: writ/session/bitbucket_client.py does not exist (ImportError).

        entry = _bb_diffstat_entry_deleted("writ/old_module.py")
        diffstat_page = _bb_diffstat_page([entry])
        client, transport = make_bb_client([_json_response(diffstat_page)])

        result = await client.get_pr_diffstat(_WS, _SLUG, _PR_ID)
        assert result[0]["path"] == "writ/old_module.py", (
            "Deleted file must resolve path from old.path (new is None)"
        )
        assert result[0]["status"] == "removed"

    @pytest.mark.asyncio
    async def test_diffstat_uses_new_path_for_rename(self) -> None:
        # [diffstat-2]: renamed file: new.path is non-None, old.path is set too.
        # new.path is authoritative.
        # RED: writ/session/bitbucket_client.py does not exist (ImportError).

        entry = {
            "new": {"path": "writ/session/remote_parse.py"},
            "old": {"path": "writ/session/old_parse.py"},
            "status": "renamed",
        }
        diffstat_page = _bb_diffstat_page([entry])
        client, transport = make_bb_client([_json_response(diffstat_page)])

        result = await client.get_pr_diffstat(_WS, _SLUG, _PR_ID)
        assert result[0]["path"] == "writ/session/remote_parse.py", (
            "Renamed file must use new.path"
        )


class TestCreateFileComment:
    """[comment-1] -- httpx mocked, no Neo4j."""

    @pytest.mark.asyncio
    async def test_create_file_comment_posts_file_level_body(self) -> None:
        # [comment-1]: create_file_comment POSTs {"content":{"raw":...},"inline":{"path":...}}
        # (file-level: inline.path required, NO from/to line). Returns created comment dict.
        # RED: writ/session/bitbucket_client.py does not exist (ImportError).

        created_comment = {"id": 77, "content": {"raw": "test body"}, "inline": {"path": "writ/foo.py"}}
        client, transport = make_bb_client([_json_response(created_comment, status_code=201)])

        result = await client.create_file_comment(_WS, _SLUG, _PR_ID, "writ/foo.py", "test body")

        # Verify request body structure.
        assert transport._seen, "Must make a POST request"
        req = transport._seen[0]
        assert req.method == "POST", f"Expected POST, got {req.method}"
        body = json.loads(req.content)
        assert "content" in body, "Request body must have 'content' key"
        assert body["content"]["raw"] == "test body", "content.raw must match body"
        assert "inline" in body, "Request body must have 'inline' key (file-level)"
        assert body["inline"]["path"] == "writ/foo.py", "inline.path must be set"
        assert "from" not in body.get("inline", {}), (
            "inline must NOT have 'from' (no line anchor)"
        )
        assert "to" not in body.get("inline", {}), (
            "inline must NOT have 'to' (no line anchor)"
        )
        # Verify returned dict.
        assert result["id"] == 77


class TestBitbucketClientAuthAndHost:
    """[auth-1], [ssrf-1] -- httpx mocked, no Neo4j."""

    @pytest.mark.asyncio
    async def test_client_uses_hardcoded_base_host(self) -> None:
        # [auth-1]: all requests go to https://api.bitbucket.org/2.0.
        # RED: writ/session/bitbucket_client.py does not exist (ImportError).

        page = _bb_pr_page(_PR_ID)
        client, transport = make_bb_client([_json_response(page)])

        await client.find_open_pr(_WS, _SLUG, _BRANCH)
        req = transport._seen[0]
        assert "api.bitbucket.org" in str(req.url), (
            f"All requests must go to api.bitbucket.org; URL was {req.url}"
        )

    @pytest.mark.asyncio
    async def test_client_token_not_in_logs(self, caplog: pytest.LogCaptureFixture) -> None:
        # [auth-1]: the token is never logged. We capture all log records at DEBUG
        # level and assert the token string does not appear.
        # RED: writ/session/bitbucket_client.py does not exist (ImportError).

        secret_token = "super-secret-token-XYZZY"
        page = _bb_pr_page(_PR_ID)
        client, transport = make_bb_client([_json_response(page)], token=secret_token)

        with caplog.at_level(logging.DEBUG):
            await client.find_open_pr(_WS, _SLUG, _BRANCH)

        for record in caplog.records:
            assert secret_token not in record.getMessage(), (
                f"Token was found in log record: {record.getMessage()!r}"
            )

    @pytest.mark.asyncio
    async def test_client_refuses_off_allowlist_redirect(self) -> None:
        # [ssrf-1]: a redirect to a non-bitbucket.org host must be refused.
        # The client should raise (not silently follow) when the redirect target
        # is outside the allowlist.
        # RED: writ/session/bitbucket_client.py does not exist (ImportError).

        # Simulate a redirect to an off-allowlist host.
        redirect_response = httpx.Response(
            302,
            headers={"Location": "https://evil.example.com/steal-data"},
        )
        client, transport = make_bb_client([redirect_response])
        # We must create the AsyncClient without follow_redirects so we can
        # test the client's own allowlist guard, OR the client handles it internally.
        # The test asserts that the call raises some exception rather than
        # returning data from the off-allowlist host.

        with pytest.raises(Exception) as exc_info:
            await client.get_pr_diffstat(_WS, _SLUG, _PR_ID)
        # The error must not be a silent success (i.e., not a returned list).
        # Accept any exception type -- the key is that it does not silently follow.
        assert exc_info.value is not None, (
            "Off-allowlist redirect must raise an exception, not silently follow"
        )


class TestListComments:
    """[list-1] -- httpx mocked, no Neo4j."""

    @pytest.mark.asyncio
    async def test_list_comments_returns_non_deleted_comments(self) -> None:
        # [list-1]: list_comments follows paginated next and returns all non-deleted
        # comment dicts.
        # RED: writ/session/bitbucket_client.py does not exist (ImportError).

        live = _bb_comment(1, "<!-- writ:file=foo.py --> reason", "foo.py")
        deleted = _bb_comment(2, "old", "bar.py", deleted=True)
        page = _bb_comments_page([live, deleted])
        client, transport = make_bb_client([_json_response(page)])

        result = await client.list_comments(_WS, _SLUG, _PR_ID)
        assert isinstance(result, list)
        ids = [c["id"] for c in result]
        assert 1 in ids, "Non-deleted comment must be in result"
        assert 2 not in ids, "Deleted comment must not be in result"


class TestUpdateComment:
    """[update-1] -- httpx mocked, no Neo4j."""

    @pytest.mark.asyncio
    async def test_update_comment_puts_content_raw(self) -> None:
        # [update-1]: update_comment PUTs {"content":{"raw":...}} to .../comments/{id}
        # and returns the updated comment dict.
        # RED: writ/session/bitbucket_client.py does not exist (ImportError).

        updated = {"id": 7, "content": {"raw": "updated body"}}
        client, transport = make_bb_client([_json_response(updated, status_code=200)])

        result = await client.update_comment(_WS, _SLUG, _PR_ID, 7, "updated body")

        assert transport._seen, "Must make a PUT request"
        req = transport._seen[0]
        assert req.method == "PUT", f"Expected PUT, got {req.method}"
        assert "/7" in str(req.url) or "7" in str(req.url), (
            f"PUT URL must contain comment_id=7; URL was {req.url}"
        )
        body = json.loads(req.content)
        assert body == {"content": {"raw": "updated body"}}, (
            f"PUT body must be {{content: {{raw: ...}}}}; got {body!r}"
        )
        assert result["id"] == 7


class TestBitbucketRateLimit:
    """[429-1], [err-1] -- httpx mocked, no Neo4j."""

    @pytest.mark.asyncio
    async def test_retries_429_bounded_then_surfaces(self) -> None:
        # [429-1]: a 429 response retries with bounded backoff and surfaces the
        # 429 error only after RATELIMIT_MAX_RETRIES are exhausted.
        # RED: writ/session/bitbucket_client.py does not exist (ImportError).

        from writ.session.bitbucket_client import BitbucketClient

        # Queue one 429 per retry plus a final 429 that should surface.
        # RATELIMIT_MAX_RETRIES = 3, so we queue 4 total 429s (3 retries + 1 final).
        responses = [httpx.Response(429)] * (BitbucketClient.RATELIMIT_MAX_RETRIES + 1)
        client, transport = make_bb_client(responses)

        # Patch asyncio.sleep to avoid actual delay in tests.
        with patch("asyncio.sleep", new=AsyncMock()):
            with pytest.raises(Exception) as exc_info:
                await client.create_file_comment(_WS, _SLUG, _PR_ID, "writ/foo.py", "body")

        # Must have retried (not raised on first 429).
        assert len(transport._seen) > 1, (
            f"Client must retry on 429; only {len(transport._seen)} request(s) made"
        )
        assert len(transport._seen) <= BitbucketClient.RATELIMIT_MAX_RETRIES + 1, (
            f"Client must not exceed RATELIMIT_MAX_RETRIES retries; "
            f"made {len(transport._seen)} requests"
        )
        # The error must eventually surface.
        assert exc_info.value is not None

    @pytest.mark.asyncio
    async def test_non_429_error_raises_immediately(self) -> None:
        # [err-1]: a non-429 non-2xx response must raise (not swallow) immediately.
        # RED: writ/session/bitbucket_client.py does not exist (ImportError).

        client, transport = make_bb_client([httpx.Response(403)])

        with pytest.raises(Exception):
            await client.create_file_comment(_WS, _SLUG, _PR_ID, "writ/foo.py", "body")

        # Must have made exactly ONE request (no retry on non-429).
        assert len(transport._seen) == 1, (
            f"Non-429 error must not retry; made {len(transport._seen)} requests"
        )

    @pytest.mark.asyncio
    async def test_500_raises_without_retry(self) -> None:
        # [err-1]: 5xx must also raise without retry.
        # RED: writ/session/bitbucket_client.py does not exist (ImportError).

        client, transport = make_bb_client([httpx.Response(500)])

        with pytest.raises(Exception):
            await client.update_comment(_WS, _SLUG, _PR_ID, 5, "body")


# ===========================================================================
# PAGINATION BOUNDARY group (ENF-POST-005)
# ===========================================================================

class TestPaginationBoundary:
    """[pag-1]: find_open_pr / list_comments cover exactly one page (no next),
    one over (one next), and well over (multiple next) without dropping items."""

    @pytest.mark.asyncio
    async def test_find_open_pr_exactly_one_page_no_next(self) -> None:
        # [pag-1]: a single full page with no 'next' key.
        # RED: writ/session/bitbucket_client.py does not exist (ImportError).

        page1 = {"values": [
            {"id": 1, "state": "OPEN", "source": {"branch": {"name": _BRANCH}}},
            {"id": 2, "state": "OPEN", "source": {"branch": {"name": _BRANCH}}},
        ]}
        client, transport = make_bb_client([_json_response(page1)])

        result = await client.find_open_pr(_WS, _SLUG, _BRANCH)
        assert result is not None, "Must return the first matching PR id"
        assert len(transport._seen) == 1, (
            "Exactly one page with no 'next' -- must make exactly 1 HTTP request"
        )

    @pytest.mark.asyncio
    async def test_find_open_pr_one_over_follows_next(self) -> None:
        # [pag-1]: first page empty + next; second page has the PR.
        # RED: writ/session/bitbucket_client.py does not exist (ImportError).

        page1 = {"values": [], "next": "https://api.bitbucket.org/2.0/repositories/a/b/pullrequests?page=2"}
        page2 = {"values": [{"id": 7, "state": "OPEN", "source": {"branch": {"name": _BRANCH}}}]}
        client, transport = make_bb_client([_json_response(page1), _json_response(page2)])

        result = await client.find_open_pr(_WS, _SLUG, _BRANCH)
        assert result == 7
        assert len(transport._seen) == 2, (
            "One-over boundary: must follow exactly one 'next' link (2 requests total)"
        )

    @pytest.mark.asyncio
    async def test_find_open_pr_well_over_follows_multiple_next(self) -> None:
        # [pag-1]: three pages; PR only on page 3.
        # RED: writ/session/bitbucket_client.py does not exist (ImportError).

        base = "https://api.bitbucket.org/2.0/repositories/a/b/pullrequests"
        page1 = {"values": [], "next": f"{base}?page=2"}
        page2 = {"values": [], "next": f"{base}?page=3"}
        page3 = {"values": [{"id": 99, "state": "OPEN", "source": {"branch": {"name": _BRANCH}}}]}
        client, transport = make_bb_client([
            _json_response(page1), _json_response(page2), _json_response(page3)
        ])

        result = await client.find_open_pr(_WS, _SLUG, _BRANCH)
        assert result == 99
        assert len(transport._seen) == 3, (
            "Well-over boundary: must follow all 'next' links (3 requests total)"
        )

    @pytest.mark.asyncio
    async def test_list_comments_exactly_one_page(self) -> None:
        # [pag-1]: single page with no 'next' key.
        # RED: writ/session/bitbucket_client.py does not exist (ImportError).

        comments = [_bb_comment(1, "body1"), _bb_comment(2, "body2")]
        page1 = _bb_comments_page(comments)
        client, transport = make_bb_client([_json_response(page1)])

        result = await client.list_comments(_WS, _SLUG, _PR_ID)
        assert len(result) == 2
        assert len(transport._seen) == 1

    @pytest.mark.asyncio
    async def test_list_comments_one_over_does_not_drop_items(self) -> None:
        # [pag-1]: two pages; no items dropped at page boundary.
        # RED: writ/session/bitbucket_client.py does not exist (ImportError).

        base = "https://api.bitbucket.org/2.0/repositories/a/b/pullrequests/42/comments"
        page1_comments = [_bb_comment(i, f"body-{i}") for i in range(1, 4)]
        page1 = _bb_comments_page(page1_comments, next_url=f"{base}?page=2")
        page2_comments = [_bb_comment(i, f"body-{i}") for i in range(4, 7)]
        page2 = _bb_comments_page(page2_comments)
        client, transport = make_bb_client([_json_response(page1), _json_response(page2)])

        result = await client.list_comments(_WS, _SLUG, _PR_ID)
        assert len(result) == 6, (
            f"list_comments must return all 6 items across 2 pages; got {len(result)}"
        )
        assert len(transport._seen) == 2

    @pytest.mark.asyncio
    async def test_list_comments_well_over_does_not_drop_items(self) -> None:
        # [pag-1]: three pages; all items collected.
        # RED: writ/session/bitbucket_client.py does not exist (ImportError).

        base = "https://api.bitbucket.org/2.0/repositories/a/b/pullrequests/42/comments"
        page1 = _bb_comments_page(
            [_bb_comment(1, "a"), _bb_comment(2, "b")],
            next_url=f"{base}?page=2",
        )
        page2 = _bb_comments_page(
            [_bb_comment(3, "c"), _bb_comment(4, "d")],
            next_url=f"{base}?page=3",
        )
        page3 = _bb_comments_page([_bb_comment(5, "e")])
        client, transport = make_bb_client([
            _json_response(page1), _json_response(page2), _json_response(page3)
        ])

        result = await client.list_comments(_WS, _SLUG, _PR_ID)
        assert len(result) == 5, (
            f"list_comments must collect all 5 items across 3 pages; got {len(result)}"
        )
        assert len(transport._seen) == 3


# ===========================================================================
# NEO4J-GATED group: get_latest_filechange_per_path
# ===========================================================================

class TestGetLatestFilechangePerPath:
    """[db-latest-1], [db-latest-2] -- requires db_clean fixture (Neo4j)."""

    @pytest.mark.asyncio
    async def test_returns_most_recent_reason_per_path(self, db_clean: Neo4jConnection) -> None:
        # [db-latest-1]: seed two FileChange records for different paths; assert
        # the method returns the correct reason for each path.
        # RED: get_latest_filechange_per_path is not yet added to Neo4jConnection.

        await db_clean.create_filechange(**_filechange_factory(
            change_id="FC-1e-path-a-001",
            project=_TEST_SCOPE,
            path="writ/session/pr_host.py",
            reason="Define PrHost protocol.",
            ts="2026-06-26T08:00:00Z",
        ))
        await db_clean.create_filechange(**_filechange_factory(
            change_id="FC-1e-path-b-001",
            project=_TEST_SCOPE,
            path="writ/session/bitbucket_client.py",
            reason="Implement BitbucketClient adapter.",
            ts="2026-06-26T09:00:00Z",
        ))

        result = await db_clean.get_latest_filechange_per_path(
            _TEST_SCOPE,
            ["writ/session/pr_host.py", "writ/session/bitbucket_client.py"],
        )

        assert "writ/session/pr_host.py" in result, (
            "get_latest_filechange_per_path must return an entry for pr_host.py"
        )
        assert "writ/session/bitbucket_client.py" in result
        assert result["writ/session/pr_host.py"]["reason"] == "Define PrHost protocol."
        assert result["writ/session/bitbucket_client.py"]["reason"] == "Implement BitbucketClient adapter."

    @pytest.mark.asyncio
    async def test_omits_paths_with_no_filechange(self, db_clean: Neo4jConnection) -> None:
        # [db-latest-1]: paths not in the DB are absent from the result.
        # RED: get_latest_filechange_per_path is not yet added.

        await db_clean.create_filechange(**_filechange_factory(
            change_id="FC-1e-omit-001",
            project=_TEST_SCOPE,
            path="writ/session/pr_comments.py",
            reason="Sync logic.",
        ))

        result = await db_clean.get_latest_filechange_per_path(
            _TEST_SCOPE,
            ["writ/session/pr_comments.py", "writ/no/such/file.py"],
        )

        assert "writ/session/pr_comments.py" in result
        assert "writ/no/such/file.py" not in result, (
            "Paths with no FileChange must be absent from the result (not None, not error)"
        )

    @pytest.mark.asyncio
    async def test_returns_latest_by_ts_for_multi_record_path(self, db_clean: Neo4jConnection) -> None:
        # [db-latest-2]: a path with two FileChange records at different ts; the
        # most-recent reason is returned, not the older one.
        # RED: get_latest_filechange_per_path is not yet added.

        path = "writ/graph/db.py"
        await db_clean.create_filechange(**_filechange_factory(
            change_id="FC-1e-multi-old",
            project=_TEST_SCOPE,
            path=path,
            reason="Old reason from earlier commit.",
            ts="2026-06-25T10:00:00Z",
        ))
        await db_clean.create_filechange(**_filechange_factory(
            change_id="FC-1e-multi-new",
            project=_TEST_SCOPE,
            path=path,
            reason="Newer reason from later commit.",
            ts="2026-06-26T10:00:00Z",
        ))

        result = await db_clean.get_latest_filechange_per_path(_TEST_SCOPE, [path])

        assert path in result
        assert result[path]["reason"] == "Newer reason from later commit.", (
            f"Expected the newer reason; got {result[path]['reason']!r}"
        )

    @pytest.mark.asyncio
    async def test_one_entry_per_path_even_with_multiple_records(self, db_clean: Neo4jConnection) -> None:
        # [db-latest-2]: result dict has exactly one entry per path, even when
        # multiple FileChange nodes share the path.
        # RED: get_latest_filechange_per_path is not yet added.

        path = "writ/cli.py"
        for i in range(3):
            await db_clean.create_filechange(**_filechange_factory(
                change_id=f"FC-1e-dup-{i:03d}",
                project=_TEST_SCOPE,
                path=path,
                reason=f"Reason {i}",
                ts=f"2026-06-26T1{i}:00:00Z",
            ))

        result = await db_clean.get_latest_filechange_per_path(_TEST_SCOPE, [path])

        assert path in result
        # The value must be a dict, not a list (one entry, not all three).
        assert isinstance(result[path], dict), (
            f"Expected a single dict per path, got {type(result[path])}"
        )

    @pytest.mark.asyncio
    async def test_includes_commit_subject_when_commit_present(self, db_clean: Neo4jConnection) -> None:
        # [db-latest-3]: when a Commit node matches the FileChange's commit_hash,
        # the result carries that commit's subject.
        path = "writ/session/harvester.py"
        await db_clean.create_commit(
            commit_hash="COMMIT1E001", project=_TEST_SCOPE,
            subject="feat: add harvester", author="alice", branch="b",
        )
        await db_clean.create_filechange(**_filechange_factory(
            change_id="FC-1e-subj-001", project=_TEST_SCOPE, path=path,
            reason="Add harvester.", commit_hash="COMMIT1E001",
        ))
        result = await db_clean.get_latest_filechange_per_path(_TEST_SCOPE, [path])
        assert result[path]["commit_subject"] == "feat: add harvester"


class TestGetRuleStatements:
    """[db-rules-1] -- requires db_clean fixture (Neo4j)."""

    @pytest.mark.asyncio
    async def test_returns_statements_for_known_ids_and_omits_unknown(self, db_clean: Neo4jConnection) -> None:
        # [db-rules-1]: get_rule_statements returns {rule_id: statement} for known
        # ids and omits unknown ids (one batched read).
        async with db_clean._driver.session(database=db_clean._database) as s:
            await (await s.run(
                "CREATE (:Rule {rule_id: 'TEST1E-RULE-001', statement: 'Do the thing safely.'})"
            )).consume()
        result = await db_clean.get_rule_statements(["TEST1E-RULE-001", "TEST1E-NOPE-999"])
        assert result.get("TEST1E-RULE-001") == "Do the thing safely."
        assert "TEST1E-NOPE-999" not in result

    @pytest.mark.asyncio
    async def test_empty_input_returns_empty(self, db_clean: Neo4jConnection) -> None:
        # [db-rules-1]: empty id list -> empty dict (no query needed).
        assert await db_clean.get_rule_statements([]) == {}


# ===========================================================================
# ORCHESTRATION group: sync_pr_comments with FakePrHost + FakeDB
# ===========================================================================

class TestSyncPrComments:
    """[sync-1] through [sync-7] -- FakePrHost + FakeDB, no Neo4j, no httpx."""

    @pytest.mark.asyncio
    async def test_creates_one_comment_per_changed_path_with_reason(self) -> None:
        # [sync-1]: sync_pr_comments reads diffstat, joins per-path reasons, and
        # creates exactly ONE file-level comment per changed path that has a reason.
        # RED: writ/session/pr_comments.py does not exist (ImportError).
        from writ.session.pr_comments import sync_pr_comments

        diffstat = [
            _bb_diffstat_entry("writ/session/pr_comments.py", "add"),
            _bb_diffstat_entry("writ/session/pr_host.py", "add"),
        ]
        reasons = {
            "writ/session/pr_comments.py": {
                "reason": "Sync logic.", "change_type": "add",
                "commit_hash": "abc", "ts": "2026-06-26T10:00:00Z",
            },
            "writ/session/pr_host.py": {
                "reason": "PrHost protocol.", "change_type": "add",
                "commit_hash": "abc", "ts": "2026-06-26T10:00:00Z",
            },
        }
        host = FakePrHost(diffstat=diffstat)
        db = FakeDB(reasons=reasons)

        counts = await sync_pr_comments(host, db, _WS, _SLUG, _TEST_SCOPE, _PR_ID)

        assert len(host.created) == 2, (
            f"Expected 2 file-level comments created; got {len(host.created)}"
        )
        assert counts.get("created") == 2, f"counts['created'] must be 2; got {counts}"
        created_paths = {c["path"] for c in host.created}
        assert "writ/session/pr_comments.py" in created_paths
        assert "writ/session/pr_host.py" in created_paths

    @pytest.mark.asyncio
    async def test_idempotent_update_not_duplicate_when_ours_present(self) -> None:
        # [sync-2]: an existing comment on this path carrying the Writ attribution is
        # updated-not-duplicated (identified by inline path + attribution, no marker).
        from writ.session.pr_comments import sync_pr_comments

        path = "writ/session/pr_comments.py"
        # Our prior comment: same inline path + the attribution signature, old body.
        existing_body = "**Why this change** -- `x` (modify)\n\nOld reason.\n\n_Posted by Writ_"
        existing = [_bb_comment(55, existing_body, path)]

        new_reason_data = {
            "reason": "New reason.", "change_type": "modify",
            "commit_hash": "def", "ts": "2026-06-26T11:00:00Z",
        }
        diffstat = [_bb_diffstat_entry(path, "modify")]
        host = FakePrHost(diffstat=diffstat, existing_comments=existing)
        db = FakeDB(reasons={path: new_reason_data})

        counts = await sync_pr_comments(host, db, _WS, _SLUG, _TEST_SCOPE, _PR_ID)

        assert len(host.created) == 0, (
            "Must not create a duplicate -- marker was found, must update"
        )
        assert len(host.updated) == 1, (
            f"Must update the existing comment; got {len(host.updated)} updates"
        )
        assert host.updated[0]["comment_id"] == 55
        assert counts.get("updated") == 1

    @pytest.mark.asyncio
    async def test_idempotent_unchanged_body_posts_nothing(self) -> None:
        # [sync-2]: if the marker is present and the body is unchanged, no update is posted.
        # RED: writ/session/pr_comments.py does not exist (ImportError).
        from writ.session.pr_comments import file_comment_body, sync_pr_comments

        path = "writ/session/pr_host.py"
        reason_data = {
            "reason": "PrHost protocol.",
            "change_type": "add",
            "commit_hash": "abc",
            "ts": "2026-06-26T10:00:00Z",
        }
        # Build the exact body that sync_pr_comments would render (no rules -> []).
        rendered = file_comment_body(path, "add", "PrHost protocol.", [], [])
        existing = [_bb_comment(66, rendered, path)]

        diffstat = [_bb_diffstat_entry(path, "add")]
        host = FakePrHost(diffstat=diffstat, existing_comments=existing)
        db = FakeDB(reasons={path: reason_data})

        counts = await sync_pr_comments(host, db, _WS, _SLUG, _TEST_SCOPE, _PR_ID)

        assert len(host.created) == 0
        assert len(host.updated) == 0, (
            "Unchanged body must not trigger an update POST/PUT"
        )
        assert counts.get("unchanged", 0) >= 1

    @pytest.mark.asyncio
    async def test_skips_path_with_no_captured_reason(self) -> None:
        # [sync-3]: a changed path with no captured reason is skipped.
        # RED: writ/session/pr_comments.py does not exist (ImportError).
        from writ.session.pr_comments import sync_pr_comments

        diffstat = [
            _bb_diffstat_entry("writ/session/pr_comments.py", "add"),  # has reason
            _bb_diffstat_entry("writ/unrelated_module.py", "modify"),  # no reason
        ]
        reasons = {
            "writ/session/pr_comments.py": {
                "reason": "Sync logic.", "change_type": "add",
                "commit_hash": "abc", "ts": "2026-06-26T10:00:00Z",
            },
        }
        host = FakePrHost(diffstat=diffstat)
        db = FakeDB(reasons=reasons)

        counts = await sync_pr_comments(host, db, _WS, _SLUG, _TEST_SCOPE, _PR_ID)

        assert len(host.created) == 1, (
            f"Only one comment must be created (the path with a reason); got {len(host.created)}"
        )
        created_paths = {c["path"] for c in host.created}
        assert "writ/unrelated_module.py" not in created_paths, (
            "Path with no reason must not receive a comment"
        )
        assert counts.get("skipped_no_reason", 0) >= 1

    @pytest.mark.asyncio
    async def test_renders_no_reason_placeholder_for_empty_reason(self) -> None:
        # [sync-4]: a path whose reason is empty must render "No reason recorded"
        # placeholder -- never a blank comment.
        # RED: writ/session/pr_comments.py does not exist (ImportError).
        from writ.session.pr_comments import NO_REASON_PLACEHOLDER, sync_pr_comments

        path = "writ/session/pr_comments.py"
        diffstat = [_bb_diffstat_entry(path, "add")]
        reasons = {
            path: {
                "reason": "",  # empty reason
                "change_type": "add",
                "commit_hash": "abc",
                "ts": "2026-06-26T10:00:00Z",
            }
        }
        host = FakePrHost(diffstat=diffstat)
        db = FakeDB(reasons=reasons)

        await sync_pr_comments(host, db, _WS, _SLUG, _TEST_SCOPE, _PR_ID)

        assert len(host.created) == 1, "Empty reason must still produce a comment"
        body = host.created[0]["body"]
        assert NO_REASON_PLACEHOLDER in body, (
            f"Comment body must contain NO_REASON_PLACEHOLDER ({NO_REASON_PLACEHOLDER!r}); "
            f"got: {body!r}"
        )
        assert body.strip(), "Comment body must not be blank"

    @pytest.mark.asyncio
    async def test_body_includes_rules_with_statements_and_no_commit_summary(self) -> None:
        # [sync-5]: the comment body includes the change type and each governing
        # rule's id AND its statement; it does NOT include a commit summary line
        # (commits stay normal; the commit is visible on the Commits tab).
        from writ.session.pr_comments import sync_pr_comments

        path = "writ/session/pr_comments.py"
        diffstat = [_bb_diffstat_entry(path, "add")]
        # cited rule ids now live on the FileChange record (cited_rule_ids), not a
        # live get_open_decisions_for_path lookup (Phase 1f snapshot change).
        reasons = {
            path: {
                "reason": "Add sync logic.",
                "change_type": "add",
                "commit_hash": "abc",
                "ts": "2026-06-26T10:00:00Z",
                "commit_subject": "feat(1e): pr comment sync",
                "cited_rule_ids": ["ARCH-BOUNDARY-001", "SEC-INJ-SSRF-001"],
            }
        }
        host = FakePrHost(diffstat=diffstat)
        db = FakeDB(
            reasons=reasons,
            statements={
                "ARCH-BOUNDARY-001": "One narrow adapter per boundary.",
                "SEC-INJ-SSRF-001": "Validate outbound hosts against an allowlist.",
            },
        )

        await sync_pr_comments(host, db, _WS, _SLUG, _TEST_SCOPE, _PR_ID)

        assert host.created, "Must create a comment"
        body = host.created[0]["body"]
        assert "add" in body.lower(), f"body must mention change_type 'add'; got: {body!r}"
        assert "ARCH-BOUNDARY-001" in body and "SEC-INJ-SSRF-001" in body
        assert "One narrow adapter per boundary." in body, (
            f"body must include the rule STATEMENT (detail), not just the id; got: {body!r}"
        )
        assert "feat(1e): pr comment sync" not in body, (
            f"body must NOT include the commit summary (it repeats the commit); got: {body!r}"
        )
        assert "Commit:" not in body, f"body must not carry a Commit line; got: {body!r}"

    @pytest.mark.asyncio
    async def test_deleted_file_commented_on_old_path(self) -> None:
        # [sync-6]: a deleted file (status=removed, new=None) must be commented
        # on its old.path.
        # RED: writ/session/pr_comments.py does not exist (ImportError).
        from writ.session.pr_comments import sync_pr_comments

        old_path = "writ/old_module.py"
        # Diffstat entry: new is None (deleted), old.path is old_path.
        # BitbucketClient.get_pr_diffstat resolves path to old.path for status=removed.
        # We return this through FakePrHost.get_pr_diffstat directly.
        diffstat = [{"path": old_path, "status": "removed"}]
        reasons = {
            old_path: {
                "reason": "Removing old module.",
                "change_type": "remove",
                "commit_hash": "abc",
                "ts": "2026-06-26T10:00:00Z",
            }
        }
        host = FakePrHost(diffstat=diffstat)
        db = FakeDB(reasons=reasons)

        await sync_pr_comments(host, db, _WS, _SLUG, _TEST_SCOPE, _PR_ID)

        assert host.created, "Must create a comment for the deleted file"
        assert host.created[0]["path"] == old_path, (
            f"Deleted file comment must use old.path={old_path!r}; "
            f"got {host.created[0]['path']!r}"
        )

    @pytest.mark.asyncio
    async def test_fails_loud_on_non_429_create_error(self) -> None:
        # [sync-7]: a non-429 error on create_file_comment must surface (re-raise)
        # and must NOT fall back to a line-level or general comment.
        # RED: writ/session/pr_comments.py does not exist (ImportError).
        from writ.session.pr_comments import sync_pr_comments

        path = "writ/session/pr_comments.py"
        diffstat = [_bb_diffstat_entry(path, "add")]
        reasons = {
            path: {
                "reason": "Sync logic.", "change_type": "add",
                "commit_hash": "abc", "ts": "2026-06-26T10:00:00Z",
            }
        }
        host = FakePrHost(diffstat=diffstat)
        host.create_error = httpx.HTTPStatusError(
            "403 Forbidden",
            request=MagicMock(),
            response=MagicMock(status_code=403),
        )
        db = FakeDB(reasons=reasons)

        with pytest.raises(Exception) as exc_info:
            await sync_pr_comments(host, db, _WS, _SLUG, _TEST_SCOPE, _PR_ID)

        assert exc_info.value is not None, "Non-429 error must surface (FAIL LOUD)"
        # No fallback comment must have been created via a second create call.
        # (The create_error fires on first create_file_comment; any further
        # comment attempt would also fail since create_error is still set.
        # The key assertion is that the exception was NOT swallowed.)
        assert len(host.updated) == 0, (
            "On a non-429 create error, no fallback update must be attempted"
        )


# ===========================================================================
# CLI group: writ pr sync
# ===========================================================================

class TestWritPrSyncCLI:
    """[cli-sync-1], [cli-sync-2], [cli-sync-3], [cli-sync-4] -- CliRunner."""

    def _make_fake_sync(self, counts: dict | None = None) -> "AsyncMock":
        """Return an AsyncMock for sync_pr_comments returning given counts."""
        mock = AsyncMock(return_value=counts or {"created": 1, "updated": 0, "unchanged": 0, "skipped_no_reason": 0})
        return mock

    def test_pr_sync_subcommand_is_registered(self) -> None:
        # [cli-sync-1]: 'writ pr sync' must be a registered command.
        # RED: writ/cli.py does not have a 'pr' sub-app yet (exit_code 2).
        from typer.testing import CliRunner
        from writ.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["pr", "--help"])
        assert result.exit_code != 2 or "pr" in result.output.lower(), (
            f"'writ pr' must be a registered command; "
            f"exit_code={result.exit_code}, output={result.output!r}"
        )
        result_sync = runner.invoke(app, ["pr", "sync", "--help"])
        assert "sync" in result_sync.output or result_sync.exit_code == 0, (
            f"'writ pr sync' must be a registered subcommand; output={result_sync.output!r}"
        )

    def test_pr_sync_runs_sync_and_reports_counts(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # [cli-sync-1]: writ pr sync resolves the open PR, runs exactly one
        # sync_pr_comments, and reports per-path counts.
        # RED: writ/cli.py not modified yet (no 'pr' sub-app).
        from typer.testing import CliRunner
        from writ.cli import app

        counts = {"created": 2, "updated": 1, "unchanged": 3, "skipped_no_reason": 0}

        with (
            patch("writ.cli.get_bitbucket_email", return_value="ci@example.com"),
            patch("writ.cli.get_bitbucket_token", return_value="test-token-xyz"),
            patch("writ.cli.sync_pr_comments", new=self._make_fake_sync(counts)),
            patch("writ.cli.BitbucketClient") as mock_bb,
            patch("writ.cli.derive_project_identity", return_value=("/repo", "https://bitbucket.org/ws/slug.git", "branch")),
            patch("writ.cli.ensure_project_registered", new=AsyncMock(return_value="test-proj")),
            patch("writ.cli.parse_bitbucket_remote", return_value=("ws", "slug")),
        ):
            mock_host = AsyncMock()
            mock_host.find_open_pr = AsyncMock(return_value=_PR_ID)
            mock_bb.return_value = mock_host

            runner = CliRunner()
            result = runner.invoke(app, ["pr", "sync"])

        # Must exit 0 and report counts.
        assert result.exit_code == 0, (
            f"'writ pr sync' must exit 0 on success; "
            f"exit_code={result.exit_code}, output={result.output!r}"
        )
        assert "2" in result.output or "created" in result.output.lower(), (
            f"Output must report counts; got: {result.output!r}"
        )

    def test_pr_sync_with_pr_id_skips_find_open_pr(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # [cli-sync-2]: writ pr sync --pr-id N targets PR N directly and skips
        # find_open_pr.
        # RED: writ/cli.py not modified yet.
        from typer.testing import CliRunner
        from writ.cli import app

        find_open_pr_mock = AsyncMock(return_value=None)

        with (
            patch("writ.cli.get_bitbucket_email", return_value="ci@example.com"),
            patch("writ.cli.get_bitbucket_token", return_value="test-token-xyz"),
            patch("writ.cli.sync_pr_comments", new=self._make_fake_sync()),
            patch("writ.cli.BitbucketClient") as mock_bb,
            patch("writ.cli.derive_project_identity", return_value=("/repo", "https://bitbucket.org/ws/slug.git", "branch")),
            patch("writ.cli.ensure_project_registered", new=AsyncMock(return_value="test-proj")),
            patch("writ.cli.parse_bitbucket_remote", return_value=("ws", "slug")),
        ):
            mock_host = AsyncMock()
            mock_host.find_open_pr = find_open_pr_mock
            mock_bb.return_value = mock_host

            runner = CliRunner()
            result = runner.invoke(app, ["pr", "sync", "--pr-id", "77"])

        assert result.exit_code == 0, (
            f"writ pr sync --pr-id 77 must exit 0; output={result.output!r}"
        )
        find_open_pr_mock.assert_not_called(), (
            "find_open_pr must NOT be called when --pr-id is given"
        )

    def test_pr_sync_clean_message_when_credentials_absent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # [cli-sync-3]: writ pr sync exits cleanly with a clear message (no
        # traceback) when the writ.toml [bitbucket] creds are absent. Patch the
        # getters (not env) so a filled-in local writ.toml cannot mask this case.
        from typer.testing import CliRunner
        from writ.cli import app

        with (
            patch("writ.cli.get_bitbucket_email", return_value=""),
            patch("writ.cli.get_bitbucket_token", return_value=""),
        ):
            runner = CliRunner()
            result = runner.invoke(app, ["pr", "sync"])

        # Must exit non-zero but cleanly -- no traceback in output.
        assert result.exit_code != 0, (
            "Must exit with a non-zero code when credentials are absent"
        )
        assert "Traceback" not in result.output, (
            f"Output must not contain a traceback; got: {result.output!r}"
        )
        output_lower = result.output.lower()
        # Require "writ.toml": the message must tell the dev the one place creds go.
        assert "writ.toml" in output_lower, (
            f"Output must point the dev at writ.toml [bitbucket]; got: {result.output!r}"
        )

    def test_pr_sync_clean_message_when_no_open_pr(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # [cli-sync-4]: writ pr sync exits cleanly with a clear message (no
        # traceback) when no open PR exists for the branch.
        # RED: writ/cli.py not modified yet.
        from typer.testing import CliRunner
        from writ.cli import app

        with (
            patch("writ.cli.get_bitbucket_email", return_value="ci@example.com"),
            patch("writ.cli.get_bitbucket_token", return_value="test-token-xyz"),
            patch("writ.cli.BitbucketClient") as mock_bb,
            patch("writ.cli.derive_project_identity", return_value=("/repo", "https://bitbucket.org/ws/slug.git", "no-pr-branch")),
            patch("writ.cli.ensure_project_registered", new=AsyncMock(return_value="test-proj")),
            patch("writ.cli.parse_bitbucket_remote", return_value=("ws", "slug")),
        ):
            mock_host = AsyncMock()
            mock_host.find_open_pr = AsyncMock(return_value=None)
            mock_bb.return_value = mock_host

            runner = CliRunner()
            result = runner.invoke(app, ["pr", "sync"])

        assert result.exit_code != 0, (
            "Must exit non-zero when no open PR is found"
        )
        assert "Traceback" not in result.output, (
            f"Output must not contain a traceback; got: {result.output!r}"
        )
        assert "no open pr" in result.output.lower() or "not found" in result.output.lower() or "branch" in result.output.lower(), (
            f"Output must mention the missing PR; got: {result.output!r}"
        )


# ===========================================================================
# CONFIG group: get_bitbucket_email / get_bitbucket_token
# ===========================================================================

class TestBitbucketConfigGetters:
    """[cfg-1] -- creds read from writ.toml [bitbucket] only (no env). No Neo4j, no HTTP."""

    @staticmethod
    def _write_toml(tmp_path, body: str) -> str:
        # Helper: write a temp writ.toml and return its path for the getter's `path` arg.
        path = tmp_path / "writ.toml"
        path.write_text(body)
        return str(path)

    def test_get_bitbucket_email_reads_toml_when_section_present(self, tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
        # [cfg-1]: get_bitbucket_email reads [bitbucket].email from writ.toml.
        from writ.config import get_bitbucket_email

        # delenv so a stray env var cannot stand in for a real toml read.
        monkeypatch.delenv("WRIT_BITBUCKET_EMAIL", raising=False)
        path = self._write_toml(tmp_path, '[bitbucket]\nemail = "f@x.com"\ntoken = "t"\n')
        assert get_bitbucket_email(path) == "f@x.com"

    def test_get_bitbucket_email_returns_none_when_section_absent(self, tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
        # [cfg-1]: None/"" when the [bitbucket] section/value is absent.
        from writ.config import get_bitbucket_email

        monkeypatch.delenv("WRIT_BITBUCKET_EMAIL", raising=False)
        path = self._write_toml(tmp_path, '[neo4j]\nuser = "neo4j"\n')
        result = get_bitbucket_email(path)
        assert result is None or result == "", (
            f"get_bitbucket_email must return None/'' when [bitbucket] absent; got {result!r}"
        )

    def test_get_bitbucket_token_reads_toml_when_section_present(self, tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
        # [cfg-1]: get_bitbucket_token reads [bitbucket].token from writ.toml.
        from writ.config import get_bitbucket_token

        monkeypatch.delenv("WRIT_BITBUCKET_TOKEN", raising=False)
        path = self._write_toml(tmp_path, '[bitbucket]\nemail = "e"\ntoken = "secret-abc"\n')
        assert get_bitbucket_token(path) == "secret-abc"

    def test_get_bitbucket_token_returns_none_when_section_absent(self, tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
        # [cfg-1]: None/"" when the [bitbucket] section/value is absent.
        from writ.config import get_bitbucket_token

        monkeypatch.delenv("WRIT_BITBUCKET_TOKEN", raising=False)
        path = self._write_toml(tmp_path, '[neo4j]\nuser = "neo4j"\n')
        result = get_bitbucket_token(path)
        assert result is None or result == "", (
            f"get_bitbucket_token must return None/'' when [bitbucket] absent; got {result!r}"
        )

    def test_credentials_read_toml_and_ignore_env_one_source_of_truth(self, tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
        # [cfg-1]: writ.toml is the single source; a WRIT_BITBUCKET_* env var is NOT read.
        # Locks in the "one place, no env" contract: env set to a different value must lose.
        from writ.config import get_bitbucket_email, get_bitbucket_token

        monkeypatch.setenv("WRIT_BITBUCKET_EMAIL", "env@x.com")
        monkeypatch.setenv("WRIT_BITBUCKET_TOKEN", "env-token")
        path = self._write_toml(
            tmp_path, '[bitbucket]\nemail = "toml@x.com"\ntoken = "toml-token"\n'
        )
        assert get_bitbucket_email(path) == "toml@x.com"
        assert get_bitbucket_token(path) == "toml-token"


# ===========================================================================
# NEW TESTS: per-file queried rules beside cited rules
# Capabilities 5, 6, 7 from plan.md / capabilities.md
# ===========================================================================

# ---------------------------------------------------------------------------
# Capability 5: get_latest_filechange_per_path returns queried_rule_ids
# Tag: [db-latest-queried-1]
# ---------------------------------------------------------------------------

class TestGetLatestFilechangePerPathQueriedRuleIds:
    """Cap [db-latest-queried-1] -- requires db_clean fixture (Neo4j).

    get_latest_filechange_per_path must project and return queried_rule_ids
    per path. The FakeDB and the real-db-shaped tests must include the key.
    """

    def test_fakedb_get_latest_includes_queried_rule_ids(self) -> None:
        # [db-latest-queried-1]: FakeDB.get_latest_filechange_per_path must include
        # queried_rule_ids in each per-path record.
        # This test uses the synchronous FakeDB double (no Neo4j needed).
        # RED: FakeDB._reasons records lack queried_rule_ids key.
        import asyncio

        path = "writ/session/pr_comments.py"
        db = FakeDB(reasons={
            path: {
                "reason": "Sync logic.",
                "change_type": "add",
                "commit_hash": "abc",
                "ts": "2026-06-26T10:00:00Z",
                "queried_rule_ids": ["ENF-Q-001", "PERF-Q-001"],
            }
        })

        result = asyncio.run(
            db.get_latest_filechange_per_path(_TEST_SCOPE, [path])
        )

        assert path in result, f"path must be in result; got {list(result.keys())}"
        record = result[path]
        assert "queried_rule_ids" in record, (
            "get_latest_filechange_per_path result must include 'queried_rule_ids' key per path"
        )
        assert record["queried_rule_ids"] == ["ENF-Q-001", "PERF-Q-001"], (
            f"queried_rule_ids must be preserved; got {record['queried_rule_ids']!r}"
        )

    @pytest.mark.asyncio
    async def test_real_db_returns_queried_rule_ids_for_path(
        self, db_clean: Neo4jConnection
    ) -> None:
        # [db-latest-queried-1]: after storing a FileChange with queried_rule_ids,
        # get_latest_filechange_per_path returns those ids in the per-path result.
        # RED: get_latest_filechange_per_path does not yet project queried_rule_ids
        # from the Cypher RETURN clause (key absent or returns empty).
        import uuid as _uuid
        path = "writ/session/pr_comments_queried_test.py"
        rule_ids = ["ENF-Q-001", "PERF-Q-001"]

        await db_clean.create_filechange(
            change_id=f"FC-1e-qri-{_uuid.uuid4().hex[:8]}",
            project=_TEST_SCOPE,
            path=path,
            change_type="add",
            reason="Test queried rule ids projection.",
            commit_hash="qri-commit-001",
            ts="2026-06-26T10:00:00Z",
            queried_rule_ids=rule_ids,
        )

        result = await db_clean.get_latest_filechange_per_path(_TEST_SCOPE, [path])

        assert path in result, (
            f"path must appear in result; keys={list(result.keys())}"
        )
        record = result[path]
        assert "queried_rule_ids" in record, (
            "get_latest_filechange_per_path must project queried_rule_ids in its RETURN clause; "
            "key absent from result dict"
        )
        assert record["queried_rule_ids"] == rule_ids, (
            f"queried_rule_ids must equal the stored list; got {record['queried_rule_ids']!r}"
        )

    @pytest.mark.asyncio
    async def test_real_db_queried_rule_ids_empty_for_older_filechange(
        self, db_clean: Neo4jConnection
    ) -> None:
        # [db-latest-queried-1]: a FileChange stored without queried_rule_ids
        # (pre-feature) yields queried_rule_ids = [] in the result (not None, not absent).
        # RED: field absent from RETURN clause or not defaulted in db.py result dict.
        import uuid as _uuid
        path = "writ/session/budget_tracking_queried_test.py"

        await db_clean.create_filechange(
            change_id=f"FC-1e-qri-old-{_uuid.uuid4().hex[:8]}",
            project=_TEST_SCOPE,
            path=path,
            change_type="modify",
            reason="Old filechange without queried ids.",
            commit_hash="qri-commit-002",
            ts="2026-06-26T09:00:00Z",
        )

        result = await db_clean.get_latest_filechange_per_path(_TEST_SCOPE, [path])

        assert path in result
        record = result[path]
        assert "queried_rule_ids" in record, (
            "result must always include queried_rule_ids (default to []) even for old FileChanges"
        )
        assert record["queried_rule_ids"] == [], (
            f"queried_rule_ids must be [] when not stored; got {record['queried_rule_ids']!r}"
        )


# ---------------------------------------------------------------------------
# Capability 6: file_comment_body renders "queried" and "cited" sections
# Tag: [body-queried-1]
# ---------------------------------------------------------------------------

class TestFileCommentBodyQueriedAndCited:
    """Cap [body-queried-1] -- pure Python, no Neo4j required.

    file_comment_body(path, change_type, reason, queried_rules, cited_rules)
    must render:
    - a "**Rules the AI was shown (queried)**" section when queried_rules non-empty
    - a "**Rules the AI cited (governing)**" section when cited_rules non-empty
    - both sections with rule_id and statement text
    - ordering: queried section first, then cited section, then attribution
    - each section omitted when the corresponding list is empty
    """

    def test_both_sections_present_when_both_lists_non_empty(self) -> None:
        # [body-queried-1]: both queried_rules and cited_rules non-empty -> both sections.
        # RED: file_comment_body still accepts only 4 args (TypeError on 5-arg call),
        # or does not yet render the two-section layout.
        from writ.session.pr_comments import file_comment_body

        queried = [{"rule_id": "ENF-Q-001", "statement": "Enforce the queried rule."}]
        cited = [{"rule_id": "ARCH-C-001", "statement": "Enforce the cited rule."}]

        body = file_comment_body(
            "writ/session/pr_comments.py", "modify", "Test reason.", queried, cited
        )

        assert "**Rules the AI was shown (queried)**" in body, (
            f"body must contain queried section header; got:\n{body}"
        )
        assert "**Rules the AI cited (governing)**" in body, (
            f"body must contain cited section header; got:\n{body}"
        )
        assert "ENF-Q-001" in body, f"queried rule id must appear in body; got:\n{body}"
        assert "ARCH-C-001" in body, f"cited rule id must appear in body; got:\n{body}"
        assert "Enforce the queried rule." in body, (
            f"queried rule statement must appear in body; got:\n{body}"
        )
        assert "Enforce the cited rule." in body, (
            f"cited rule statement must appear in body; got:\n{body}"
        )

    def test_queried_section_omitted_when_list_empty(self) -> None:
        # [body-queried-1]: empty queried_rules -> no queried section header.
        # RED: file_comment_body does not yet accept 5 args (TypeError).
        from writ.session.pr_comments import file_comment_body

        cited = [{"rule_id": "ARCH-C-001", "statement": "Enforce the cited rule."}]
        body = file_comment_body(
            "writ/session/pr_comments.py", "modify", "Test reason.", [], cited
        )

        assert "**Rules the AI was shown (queried)**" not in body, (
            "queried section must be omitted when queried_rules is empty"
        )
        assert "**Rules the AI cited (governing)**" in body, (
            "cited section must still appear when cited_rules is non-empty"
        )

    def test_cited_section_omitted_when_list_empty(self) -> None:
        # [body-queried-1]: empty cited_rules -> no cited section header.
        # RED: file_comment_body does not yet accept 5 args (TypeError).
        from writ.session.pr_comments import file_comment_body

        queried = [{"rule_id": "ENF-Q-001", "statement": "Enforce the queried rule."}]
        body = file_comment_body(
            "writ/session/pr_comments.py", "modify", "Test reason.", queried, []
        )

        assert "**Rules the AI was shown (queried)**" in body, (
            "queried section must appear when queried_rules is non-empty"
        )
        assert "**Rules the AI cited (governing)**" not in body, (
            "cited section must be omitted when cited_rules is empty"
        )

    def test_queried_section_before_cited_section(self) -> None:
        # [body-queried-1]: queried section appears before cited section in the body.
        # RED: wrong ordering or sections absent (TypeError / assertion failure).
        from writ.session.pr_comments import file_comment_body

        queried = [{"rule_id": "ENF-Q-001", "statement": "Queried stmt."}]
        cited = [{"rule_id": "ARCH-C-001", "statement": "Cited stmt."}]
        body = file_comment_body(
            "writ/session/pr_comments.py", "modify", "Test reason.", queried, cited
        )

        queried_pos = body.find("**Rules the AI was shown (queried)**")
        cited_pos = body.find("**Rules the AI cited (governing)**")
        assert queried_pos >= 0 and cited_pos >= 0, (
            f"both sections must be present; queried_pos={queried_pos}, cited_pos={cited_pos}"
        )
        assert queried_pos < cited_pos, (
            "queried section must appear before cited section in the rendered body"
        )

    def test_attribution_line_present_after_sections(self) -> None:
        # [body-queried-1]: the _ATTRIBUTION line must be present (and after both sections).
        # RED: file_comment_body does not yet accept 5 args (TypeError).
        from writ.session.pr_comments import file_comment_body, _ATTRIBUTION

        queried = [{"rule_id": "ENF-Q-001", "statement": "Queried."}]
        cited = [{"rule_id": "ARCH-C-001", "statement": "Cited."}]
        body = file_comment_body(
            "writ/session/pr_comments.py", "modify", "Test reason.", queried, cited
        )

        assert _ATTRIBUTION in body, (
            f"_ATTRIBUTION must appear in body; got:\n{body}"
        )
        attr_pos = body.find(_ATTRIBUTION)
        cited_pos = body.find("**Rules the AI cited (governing)**")
        assert attr_pos > cited_pos, (
            "_ATTRIBUTION must appear after the cited section"
        )

    def test_both_sections_empty_attribution_still_present(self) -> None:
        # [body-queried-1]: when both lists empty, no rule sections but attribution present.
        # RED: new 5-arg signature not yet implemented (TypeError).
        from writ.session.pr_comments import file_comment_body, _ATTRIBUTION

        body = file_comment_body(
            "writ/session/pr_comments.py", "modify", "Test reason.", [], []
        )
        assert "**Rules the AI was shown (queried)**" not in body
        assert "**Rules the AI cited (governing)**" not in body
        assert _ATTRIBUTION in body, "attribution must be present even when both lists empty"


# ---------------------------------------------------------------------------
# Capability 7: sync_pr_comments fetches statements for queried+cited union
# Tag: [sync-queried-1]
# ---------------------------------------------------------------------------

class TestSyncPrCommentsQueriedAndCited:
    """Cap [sync-queried-1] -- FakePrHost + extended FakeDB, no Neo4j.

    sync_pr_comments must:
    - collect queried_rule_ids from each FileChange record
    - union them with the Decision's governing_rule_ids (cited)
    - fetch statements for the full union in ONE get_rule_statements call
    - render both sections in the posted comment body
    """

    class _FakeDBWithQueried:
        """Extended FakeDB that returns queried_rule_ids per path and tracks
        get_rule_statements calls so we can assert ONE batched call was made.

        cited ids now come from each record's cited_rule_ids (Phase 1f snapshot),
        so this double no longer implements get_open_decisions_for_path.
        """

        def __init__(
            self,
            reasons: dict,
            statements: dict | None = None,
        ) -> None:
            self._reasons = reasons
            self._statements: dict = statements or {}
            self.get_rule_statements_calls: list[list[str]] = []

        async def get_latest_filechange_per_path(self, project, paths):
            return {p: self._reasons[p] for p in paths if p in self._reasons}

        async def get_rule_statements(self, rule_ids: list) -> dict:
            self.get_rule_statements_calls.append(list(rule_ids))
            return {rid: self._statements.get(rid, "") for rid in rule_ids}

    @pytest.mark.asyncio
    async def test_single_batched_call_for_union_of_queried_and_cited(self) -> None:
        # [sync-queried-1]: get_rule_statements is called exactly ONCE with the
        # deduped union of queried_rule_ids and governing_rule_ids (cited).
        # RED: sync_pr_comments does not yet collect queried_ids_by_path from the
        # FileChange record or does not union them (assertion failure on call count
        # or missing ids in the union arg).
        from writ.session.pr_comments import sync_pr_comments

        path = "writ/session/pr_comments.py"
        queried_ids = ["ENF-Q-001", "ENF-Q-002"]
        cited_ids = ["ARCH-C-001"]

        diffstat = [_bb_diffstat_entry(path, "modify")]
        reasons = {
            path: {
                "reason": "Sync logic.",
                "change_type": "modify",
                "commit_hash": "abc",
                "ts": "2026-06-26T10:00:00Z",
                "queried_rule_ids": queried_ids,
                "cited_rule_ids": cited_ids,
            }
        }
        statements = {
            "ENF-Q-001": "Queried rule one.",
            "ENF-Q-002": "Queried rule two.",
            "ARCH-C-001": "Cited rule one.",
        }

        db = self._FakeDBWithQueried(
            reasons=reasons,
            statements=statements,
        )
        host = FakePrHost(diffstat=diffstat)

        await sync_pr_comments(host, db, _WS, _SLUG, _TEST_SCOPE, _PR_ID)

        assert len(db.get_rule_statements_calls) == 1, (
            f"get_rule_statements must be called exactly ONCE (batched); "
            f"got {len(db.get_rule_statements_calls)} calls: {db.get_rule_statements_calls}"
        )
        called_ids = set(db.get_rule_statements_calls[0])
        expected_ids = {"ENF-Q-001", "ENF-Q-002", "ARCH-C-001"}
        assert called_ids == expected_ids, (
            f"get_rule_statements must be called with the full union of queried+cited ids; "
            f"expected {expected_ids}, got {called_ids}"
        )

    @pytest.mark.asyncio
    async def test_posted_body_contains_both_sections(self) -> None:
        # [sync-queried-1]: the posted comment body contains BOTH the
        # "queried" section and the "cited" section when both sources provide ids.
        # RED: sync_pr_comments does not yet pass queried_rules to file_comment_body
        # (missing section in rendered body).
        from writ.session.pr_comments import sync_pr_comments

        path = "writ/session/pr_comments.py"
        queried_ids = ["ENF-Q-001"]
        cited_ids = ["ARCH-C-001"]

        diffstat = [_bb_diffstat_entry(path, "modify")]
        reasons = {
            path: {
                "reason": "Test both sections.",
                "change_type": "modify",
                "commit_hash": "abc",
                "ts": "2026-06-26T10:00:00Z",
                "queried_rule_ids": queried_ids,
                "cited_rule_ids": cited_ids,
            }
        }
        statements = {
            "ENF-Q-001": "The queried rule statement.",
            "ARCH-C-001": "The cited rule statement.",
        }

        db = self._FakeDBWithQueried(
            reasons=reasons,
            statements=statements,
        )
        host = FakePrHost(diffstat=diffstat)

        await sync_pr_comments(host, db, _WS, _SLUG, _TEST_SCOPE, _PR_ID)

        assert len(host.created) == 1, (
            f"Expected 1 comment created; got {len(host.created)}"
        )
        body = host.created[0]["body"]
        assert "**Rules the AI was shown (queried)**" in body, (
            f"posted body must contain queried section; got:\n{body}"
        )
        assert "**Rules the AI cited (governing)**" in body, (
            f"posted body must contain cited section; got:\n{body}"
        )
        assert "The queried rule statement." in body, (
            f"queried rule statement must appear in posted body; got:\n{body}"
        )
        assert "The cited rule statement." in body, (
            f"cited rule statement must appear in posted body; got:\n{body}"
        )

    @pytest.mark.asyncio
    async def test_no_queried_section_when_filechange_has_empty_queried_ids(self) -> None:
        # [sync-queried-1]: when the FileChange record has queried_rule_ids = [],
        # the queried section is omitted (not rendered as an empty section).
        # RED: same as above -- sync not yet wired.
        from writ.session.pr_comments import sync_pr_comments

        path = "writ/session/pr_comments.py"
        cited_ids = ["ARCH-C-001"]

        diffstat = [_bb_diffstat_entry(path, "modify")]
        reasons = {
            path: {
                "reason": "Test no queried ids.",
                "change_type": "modify",
                "commit_hash": "abc",
                "ts": "2026-06-26T10:00:00Z",
                "queried_rule_ids": [],
                "cited_rule_ids": cited_ids,
            }
        }
        statements = {"ARCH-C-001": "The cited rule statement."}

        db = self._FakeDBWithQueried(
            reasons=reasons,
            statements=statements,
        )
        host = FakePrHost(diffstat=diffstat)

        await sync_pr_comments(host, db, _WS, _SLUG, _TEST_SCOPE, _PR_ID)

        assert len(host.created) == 1
        body = host.created[0]["body"]
        assert "**Rules the AI was shown (queried)**" not in body, (
            "queried section must be omitted when queried_rule_ids is empty"
        )
        assert "**Rules the AI cited (governing)**" in body, (
            "cited section must still appear when cited ids are present"
        )


# ===========================================================================
# HARDENING PASS: adversarial-review additions
# ===========================================================================

# ---------------------------------------------------------------------------
# Item 3: sync_pr_comments -- deduped union when same id in both queried+cited
# ---------------------------------------------------------------------------

class TestSyncPrCommentsQueriedCitedDedup:
    """Item 3: shared rule_id in queried and cited must not be duplicated in the
    get_rule_statements call arg."""

    class _FakeDBTrackingCalls:
        """Minimal FakeDB that records every get_rule_statements invocation.

        cited ids now come from each record's cited_rule_ids (Phase 1f snapshot),
        so this double no longer implements get_open_decisions_for_path.
        """

        def __init__(self, reasons, statements=None):
            self._reasons = reasons
            self._statements = statements or {}
            self.get_rule_statements_calls: list[list] = []

        async def get_latest_filechange_per_path(self, project, paths):
            return {p: self._reasons[p] for p in paths if p in self._reasons}

        async def get_rule_statements(self, rule_ids):
            self.get_rule_statements_calls.append(list(rule_ids))
            return {rid: self._statements.get(rid, "") for rid in rule_ids}

    @pytest.mark.asyncio
    async def test_shared_id_appears_exactly_once_in_union_arg(self) -> None:
        # [sync-queried-1] item 3: when rule "SHARED-001" is in BOTH
        # FileChange.queried_rule_ids AND Decision.governing_rule_ids (cited),
        # get_rule_statements must be called with "SHARED-001" appearing exactly once.
        # RED: sync_pr_comments not yet wired for queried ids (wrong union or list-concat).
        from writ.session.pr_comments import sync_pr_comments

        path = "writ/session/pr_comments.py"
        shared_id = "SHARED-001"
        queried_only_id = "QUERIED-ONLY-001"
        cited_only_id = "CITED-ONLY-001"

        diffstat = [_bb_diffstat_entry(path, "modify")]
        reasons = {
            path: {
                "reason": "Dedup test.",
                "change_type": "modify",
                "commit_hash": "abc",
                "ts": "2026-06-26T10:00:00Z",
                "queried_rule_ids": [shared_id, queried_only_id],
                "cited_rule_ids": [shared_id, cited_only_id],
            }
        }
        statements = {
            shared_id: "The shared rule.",
            queried_only_id: "Queried only rule.",
            cited_only_id: "Cited only rule.",
        }
        db = self._FakeDBTrackingCalls(
            reasons=reasons,
            statements=statements,
        )
        host = FakePrHost(diffstat=diffstat)

        await sync_pr_comments(host, db, _WS, _SLUG, _TEST_SCOPE, _PR_ID)

        assert len(db.get_rule_statements_calls) == 1, (
            f"get_rule_statements must be called exactly once; got {len(db.get_rule_statements_calls)}"
        )
        called_ids = db.get_rule_statements_calls[0]
        called_ids_set = set(called_ids)
        # All three distinct ids must be present.
        assert called_ids_set == {shared_id, queried_only_id, cited_only_id}, (
            f"union must contain all 3 distinct ids; got {called_ids_set}"
        )
        # The shared id must appear exactly once (set-union, not list-concat).
        assert called_ids.count(shared_id) == 1, (
            f"shared id '{shared_id}' must appear exactly once in the union arg (deduped); "
            f"got count={called_ids.count(shared_id)}, full arg={called_ids}"
        )


# ---------------------------------------------------------------------------
# Item 7: file_comment_body bullet format -- bold id + " -- " separator
# ---------------------------------------------------------------------------

class TestFileCommentBodyBulletFormat:
    """Item 7: rendered rule bullets must match `- **<id>** -- <statement>`."""

    def test_queried_rule_bullet_format(self) -> None:
        # [body-queried-1] item 7: a queried rule bullet must be exactly
        # `- **<id>** -- <statement>` (bold id, space-hyphen-hyphen-space, statement).
        # RED: file_comment_body does not yet accept 5 args (TypeError).
        from writ.session.pr_comments import file_comment_body

        queried = [{"rule_id": "ENF-Q-001", "statement": "Enforce the queried rule."}]
        body = file_comment_body(
            "writ/session/pr_comments.py", "modify", "Test reason.", queried, []
        )

        expected_bullet = "- **ENF-Q-001** -- Enforce the queried rule."
        assert expected_bullet in body, (
            f"queried rule bullet must be exactly {expected_bullet!r}; "
            f"body excerpt:\n{body}"
        )

    def test_cited_rule_bullet_format(self) -> None:
        # [body-queried-1] item 7: a cited rule bullet must be exactly
        # `- **<id>** -- <statement>` (same format as queried).
        # RED: file_comment_body does not yet accept 5 args (TypeError).
        from writ.session.pr_comments import file_comment_body

        cited = [{"rule_id": "ARCH-C-001", "statement": "Enforce the cited rule."}]
        body = file_comment_body(
            "writ/session/pr_comments.py", "modify", "Test reason.", [], cited
        )

        expected_bullet = "- **ARCH-C-001** -- Enforce the cited rule."
        assert expected_bullet in body, (
            f"cited rule bullet must be exactly {expected_bullet!r}; "
            f"body excerpt:\n{body}"
        )

    def test_bullet_uses_double_hyphen_not_colon(self) -> None:
        # [body-queried-1] item 7: the separator between id and statement must be
        # " -- " (space-hyphen-hyphen-space), not a colon or other character.
        # RED: file_comment_body does not yet accept 5 args (TypeError).
        from writ.session.pr_comments import file_comment_body

        rule_id = "ENF-SEP-001"
        statement = "The separator must be double-hyphen."
        queried = [{"rule_id": rule_id, "statement": statement}]
        body = file_comment_body(
            "writ/session/pr_comments.py", "modify", "Reason.", queried, []
        )

        # Must contain the bold id.
        assert f"**{rule_id}**" in body, f"rule id must be bold; got:\n{body}"
        # Must use " -- " separator, not ": ".
        assert f"**{rule_id}** -- {statement}" in body, (
            f"separator must be ' -- '; expected '**{rule_id}** -- {statement}'; "
            f"body excerpt:\n{body}"
        )
        assert f"**{rule_id}**: {statement}" not in body, (
            "separator must NOT be a colon"
        )


# ===========================================================================
# Phase 1f: cited_rule_ids from FileChange snapshot + db cited_rule_ids field
# Capabilities from plan.md Phase 1f / capabilities.md
# ===========================================================================

# ---------------------------------------------------------------------------
# DB capability: get_latest_filechange_per_path returns cited_rule_ids
# Tags:
#   [1f-db-cited-1] returns cited_rule_ids for a path
#   [1f-db-cited-2] returns [] for an old FileChange node lacking the property
# ---------------------------------------------------------------------------

class TestGetLatestFilechangePerPathCitedRuleIds:
    """Caps [1f-db-cited-1], [1f-db-cited-2] (requires db_clean, Neo4j).

    get_latest_filechange_per_path must project and return cited_rule_ids per
    path. For old FileChange nodes that predate the field, the result must be
    [] (not absent, not None).

    RED: db.py does not yet project cited_rule_ids in its RETURN clause
    (key absent from the returned dict or value is None).
    """

    @pytest.mark.asyncio
    async def test_returns_cited_rule_ids_for_path(
        self, db_clean: Neo4jConnection
    ) -> None:
        # [1f-db-cited-1]: a FileChange stored with cited_rule_ids must have those
        # ids returned by get_latest_filechange_per_path.
        # RED: cited_rule_ids not in the Cypher RETURN clause (key absent).
        import uuid as _uuid

        path = "writ/session/pr_comments_cited_test.py"
        cited_ids = ["ARCH-CITED-001", "ERR-CITED-002"]

        await db_clean.create_filechange(
            change_id=f"FC-1f-cited-{_uuid.uuid4().hex[:8]}",
            project=_TEST_SCOPE,
            path=path,
            change_type="modify",
            reason="Test cited_rule_ids projection.",
            commit_hash="cited-commit-001",
            ts="2026-06-27T10:00:00Z",
            cited_rule_ids=cited_ids,
        )

        result = await db_clean.get_latest_filechange_per_path(_TEST_SCOPE, [path])

        assert path in result, (
            f"path must appear in result; keys={list(result.keys())}"
        )
        record = result[path]
        assert "cited_rule_ids" in record, (
            "get_latest_filechange_per_path must project cited_rule_ids in its "
            "RETURN clause; key absent from result dict"
        )
        assert record["cited_rule_ids"] == cited_ids, (
            f"cited_rule_ids must equal the stored list; got {record['cited_rule_ids']!r}"
        )

    @pytest.mark.asyncio
    async def test_returns_empty_list_for_old_node_lacking_property(
        self, db_clean: Neo4jConnection
    ) -> None:
        # [1f-db-cited-2]: a FileChange stored without cited_rule_ids (pre-feature
        # node) must yield cited_rule_ids == [] in the result (not None, not absent).
        # The `row.get(...) or []` guard in db.py ensures old nodes are backward-compat.
        # RED: field absent from RETURN clause or not defaulted in the result dict.
        import uuid as _uuid

        path = "writ/session/old_filechange_cited_test.py"

        await db_clean.create_filechange(
            change_id=f"FC-1f-old-{_uuid.uuid4().hex[:8]}",
            project=_TEST_SCOPE,
            path=path,
            change_type="add",
            reason="Old filechange without cited_rule_ids.",
            commit_hash="cited-commit-002",
            ts="2026-06-27T09:00:00Z",
        )

        result = await db_clean.get_latest_filechange_per_path(_TEST_SCOPE, [path])

        assert path in result
        record = result[path]
        assert "cited_rule_ids" in record, (
            "result must always include cited_rule_ids (defaulted to []) even for "
            "old FileChanges that lack the property in Neo4j"
        )
        assert record["cited_rule_ids"] == [], (
            f"cited_rule_ids must be [] for old nodes lacking the property; "
            f"got {record['cited_rule_ids']!r}"
        )


# ---------------------------------------------------------------------------
# SYNC capability: cited from FileChange snapshot, not live open-decision lookup
# Tags:
#   [1f-sync-cited-1] sync reads cited from the FileChange snapshot
#   [1f-sync-cited-2] cited renders even when governing Decision is already RESOLVED
#   [1f-sync-cited-3] get_rule_statements called exactly once with queried union cited
#
# IMPLEMENTATION NOTE: sync_pr_comments now reads cited from the FileChange record's
# cited_rule_ids, not from a live get_open_decisions_for_path lookup. The dead
# get_open_decisions_for_path method and _governing_rules field were removed from the
# sync doubles (FakeDB, _FakeDBWithQueried, _FakeDBTrackingCalls); their cited data now
# lives on the record. _FakeDBWithRecordCited (below) keeps get_open_decisions_for_path
# returning [] on purpose: it proves the cited section renders from the record even when
# the live lookup is empty (the regression this feature fixes).
# ---------------------------------------------------------------------------

class _FakeDBWithRecordCited:
    """Test double for the Phase 1f snapshot-cited tests.

    get_latest_filechange_per_path returns records that CARRY cited_rule_ids.
    get_open_decisions_for_path returns [] (simulating a resolved Decision).
    This double proves sync reads cited from the record, not the live lookup.

    Call log on get_rule_statements so tests can assert exactly-one batched call.
    """

    def __init__(
        self,
        reasons: dict,
        statements: dict | None = None,
    ) -> None:
        # reasons: {path -> {reason, change_type, commit_hash, ts,
        #                     queried_rule_ids, cited_rule_ids}}
        self._reasons: dict = reasons
        self._statements: dict = statements or {}
        self.get_rule_statements_calls: list[list[str]] = []

    async def get_latest_filechange_per_path(self, project: str, paths: list[str]) -> dict:
        return {p: self._reasons[p] for p in paths if p in self._reasons}

    async def get_open_decisions_for_path(self, project: str, path: str) -> list:
        # Always returns [] to simulate a resolved Decision.
        # This is the regression this feature fixes: the live lookup returns []
        # after resolve_file_claims runs, so cited rendered empty before this fix.
        return []

    async def get_rule_statements(self, rule_ids: list[str]) -> dict:
        self.get_rule_statements_calls.append(list(rule_ids))
        return {rid: self._statements.get(rid, "") for rid in rule_ids}


class TestSyncPrCommentsCitedFromRecord:
    """Caps [1f-sync-cited-1], [1f-sync-cited-2], [1f-sync-cited-3].

    The CRITICAL regression test for Phase 1f: after the fix, sync must render
    the cited section from the FileChange record's cited_rule_ids, not from a
    live get_open_decisions_for_path call that returns [] for resolved Decisions.

    These tests are RED now because current pr_comments.py reads cited from the
    live lookup (which returns [] from _FakeDBWithRecordCited) -> the cited
    section is absent from the rendered body -> the assertions fail for the
    right reason.

    After the implement phase changes pr_comments.py to read cited from
    record.get("cited_rule_ids"), these tests turn GREEN.
    """

    @pytest.mark.asyncio
    async def test_cited_renders_from_record_when_open_decision_lookup_returns_empty(
        self,
    ) -> None:
        # [1f-sync-cited-1], [1f-sync-cited-2]: the regression case.
        #
        # The FileChange record carries cited_rule_ids = ["ARCH-CITED-001"].
        # get_open_decisions_for_path returns [] (Decision already resolved).
        # After the fix: the comment body must contain the "Rules the AI cited"
        # section with ARCH-CITED-001.
        # RED: current code reads cited from the live lookup (returns []) -> body
        # lacks the cited section -> "**Rules the AI cited (governing)**" absent.
        from writ.session.pr_comments import sync_pr_comments

        path = "writ/session/pr_comments.py"
        cited_ids = ["ARCH-CITED-001"]
        statements = {"ARCH-CITED-001": "Ensure backward compatibility of DB schema."}

        diffstat = [_bb_diffstat_entry(path, "modify")]
        reasons = {
            path: {
                "reason": "Update sync to read cited from record.",
                "change_type": "modify",
                "commit_hash": "abc123",
                "ts": "2026-06-27T10:00:00Z",
                "queried_rule_ids": [],
                "cited_rule_ids": cited_ids,
            }
        }

        db = _FakeDBWithRecordCited(reasons=reasons, statements=statements)
        host = FakePrHost(diffstat=diffstat)

        await sync_pr_comments(host, db, _WS, _SLUG, _TEST_SCOPE, _PR_ID)

        assert len(host.created) == 1, (
            f"Expected 1 comment created; got {len(host.created)}"
        )
        body = host.created[0]["body"]
        assert "**Rules the AI cited (governing)**" in body, (
            f"cited section must render from the FileChange record's cited_rule_ids, "
            f"NOT from the live open-decision lookup (which returns []); "
            f"body was:\n{body}"
        )
        assert "ARCH-CITED-001" in body, (
            f"cited rule id must appear in body; got:\n{body}"
        )
        assert "Ensure backward compatibility of DB schema." in body, (
            f"cited rule statement must appear in body; got:\n{body}"
        )

    @pytest.mark.asyncio
    async def test_get_rule_statements_called_once_with_queried_union_cited(
        self,
    ) -> None:
        # [1f-sync-cited-3]: get_rule_statements is called exactly once with the
        # union of queried_rule_ids and cited_rule_ids from the record.
        # get_open_decisions_for_path returns [] (resolved Decision).
        # RED: current code reads cited from the live lookup, so cited_ids is []
        # -> the union only contains the queried ids -> ARCH-CITED-001 is missing
        # from the get_rule_statements call arg.
        from writ.session.pr_comments import sync_pr_comments

        path = "writ/session/pr_comments.py"
        queried_ids = ["ENF-QUERIED-001"]
        cited_ids = ["ARCH-CITED-001"]
        statements = {
            "ENF-QUERIED-001": "Queried rule statement.",
            "ARCH-CITED-001": "Cited rule statement.",
        }

        diffstat = [_bb_diffstat_entry(path, "modify")]
        reasons = {
            path: {
                "reason": "Test single batched call.",
                "change_type": "modify",
                "commit_hash": "abc123",
                "ts": "2026-06-27T10:00:00Z",
                "queried_rule_ids": queried_ids,
                "cited_rule_ids": cited_ids,
            }
        }

        db = _FakeDBWithRecordCited(reasons=reasons, statements=statements)
        host = FakePrHost(diffstat=diffstat)

        await sync_pr_comments(host, db, _WS, _SLUG, _TEST_SCOPE, _PR_ID)

        assert len(db.get_rule_statements_calls) == 1, (
            f"get_rule_statements must be called exactly ONCE (batched); "
            f"got {len(db.get_rule_statements_calls)} calls"
        )
        called_ids = set(db.get_rule_statements_calls[0])
        expected_ids = {"ENF-QUERIED-001", "ARCH-CITED-001"}
        assert called_ids == expected_ids, (
            f"get_rule_statements must be called with the full union of queried+cited ids "
            f"read from the RECORD (not from the live lookup); "
            f"expected {expected_ids}, got {called_ids}"
        )

    @pytest.mark.asyncio
    async def test_both_queried_and_cited_sections_render_from_record(
        self,
    ) -> None:
        # [1f-sync-cited-1]: comprehensive body-content test. Both queried and cited
        # sections come from the record; get_open_decisions_for_path returns [].
        # RED: cited section absent (live lookup returns []).
        from writ.session.pr_comments import sync_pr_comments

        path = "writ/session/pr_comments.py"
        statements = {
            "ENF-QUERIED-001": "The queried rule.",
            "ARCH-CITED-001": "The cited rule.",
        }

        diffstat = [_bb_diffstat_entry(path, "modify")]
        reasons = {
            path: {
                "reason": "Both sections from record.",
                "change_type": "modify",
                "commit_hash": "deadbeef",
                "ts": "2026-06-27T10:00:00Z",
                "queried_rule_ids": ["ENF-QUERIED-001"],
                "cited_rule_ids": ["ARCH-CITED-001"],
            }
        }

        db = _FakeDBWithRecordCited(reasons=reasons, statements=statements)
        host = FakePrHost(diffstat=diffstat)

        await sync_pr_comments(host, db, _WS, _SLUG, _TEST_SCOPE, _PR_ID)

        assert host.created, "Must create a comment"
        body = host.created[0]["body"]
        assert "**Rules the AI was shown (queried)**" in body, (
            f"queried section must be present; body:\n{body}"
        )
        assert "**Rules the AI cited (governing)**" in body, (
            f"cited section must be present (from record, not live lookup); body:\n{body}"
        )
        assert "The queried rule." in body, (
            f"queried rule statement must appear; body:\n{body}"
        )
        assert "The cited rule." in body, (
            f"cited rule statement must appear; body:\n{body}"
        )
