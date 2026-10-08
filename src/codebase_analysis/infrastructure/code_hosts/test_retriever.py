"""Retrieve remote test candidates using path heuristics and change relevance."""

from __future__ import annotations

import base64
from urllib.parse import quote, urlencode

from codebase_analysis.domain.models import ExistingTest, PullRequest
from codebase_analysis.domain.paths import is_java_test_path
from codebase_analysis.infrastructure.code_hosts.api import GitHubApi, GitLabApi
from codebase_analysis.infrastructure.errors import RemoteError


def _is_test_path(path: str) -> bool:
    parts = path.lower().split("/")
    name = parts[-1]
    return (
        is_java_test_path(path)
        or
        any(part in {"test", "tests", "__tests__", "spec", "specs"} for part in parts[:-1])
        or name.startswith("test_")
        or name.endswith(("_test.py", "_spec.rb", ".test.js", ".spec.js", ".test.ts", ".spec.ts", ".test.tsx", ".spec.tsx"))
    )


def _test_score(path: str, changed_paths: tuple[str, ...]) -> tuple[int, str]:
    name = path.rsplit("/", 1)[-1].lower()
    stems = {changed.rsplit("/", 1)[-1].rsplit(".", 1)[0].lower() for changed in changed_paths}
    score = sum(stem in name for stem in stems if stem)
    if path in changed_paths:
        score += 10
    return (-score, path)


def _select_candidates(entries: list[dict], changed_paths: tuple[str, ...], preferred: tuple[str, ...]) -> list[dict]:
    changed_tests = [item for item in entries if item["path"] in changed_paths]
    candidates = [item for item in entries if item["path"] in preferred or not changed_tests or item in changed_tests]
    candidates.sort(key=lambda item: (item["path"] not in preferred, _test_score(item["path"], changed_paths)))
    return candidates


class GitHubTestRetriever:
    """Read test candidates from a GitHub PR's source commit without cloning."""

    def __init__(self, api: GitHubApi, suffix: str | None = None) -> None:
        """Configure access to the repository and any source fork.

        Args:
            api: GitHub API client with permission to read the source repository.
            suffix: Optional file extension filter for the configured language.
        """
        self.api = api
        self.suffix = suffix

    def fetch(self, pull_request: PullRequest, limit: int, preferred_paths: tuple[str, ...] = ()) -> tuple[tuple[ExistingTest, ...], int]:
        """Find candidate paths and retrieve a bounded set of test blobs.

        Candidates are ranked by changed-file names and exact changed paths.
        Contents are decoded as UTF-8 with replacement for invalid bytes.

        Args:
            pull_request: Metadata specifying the head commit and source repository.
            limit: Positive maximum number of candidate files to retrieve.
            preferred_paths: Observed caller files to prioritize within the limit.

        Returns:
            Retrieved files in rank order and the total candidate count.

        Raises:
            RemoteError: Retrieval fails, the tree is truncated, or a blob
                uses an unsupported encoding.
            KeyError: Required metadata is absent from the API response.
        """
        repository = pull_request.head_repository or self.api.repository
        commit = self.api.get(f"/git/commits/{quote(pull_request.head_ref, safe='')}", repository)
        tree = self.api.get(f"/git/trees/{quote(commit['tree']['sha'], safe='')}?recursive=1", repository)
        if tree.get("truncated"):
            raise RemoteError("GitHub repository tree was truncated")
        changed_paths = tuple(file.path for file in pull_request.files)
        candidates = [
            item for item in tree["tree"]
            if item["type"] == "blob" and (_is_test_path(item["path"]) or item["path"] in preferred_paths)
            and (self.suffix is None or item["path"].endswith(self.suffix))
        ]
        candidates = _select_candidates(candidates, changed_paths, preferred_paths)
        tests: list[ExistingTest] = []
        for item in candidates[:limit]:
            blob = self.api.get(f"/git/blobs/{quote(item['sha'], safe='')}", repository)
            if blob.get("encoding") != "base64":
                raise RemoteError(f"Unexpected GitHub blob encoding for {item['path']}")
            content = base64.b64decode(blob["content"], validate=False).decode("utf-8", errors="replace")
            tests.append(ExistingTest(item["path"], content))
        return tuple(tests), len(candidates)


class GitLabTestRetriever:
    """Read test candidates from a GitLab MR's source commit without cloning."""

    def __init__(self, api: GitLabApi, suffix: str | None = None) -> None:
        """Configure access to the project and any source fork.

        Args:
            api: GitLab API client with permission to read the source project.
            suffix: Optional file extension filter for the configured language.
        """
        self.api = api
        self.suffix = suffix

    def fetch(self, pull_request: PullRequest, limit: int, preferred_paths: tuple[str, ...] = ()) -> tuple[tuple[ExistingTest, ...], int]:
        """Find candidate paths and retrieve a bounded set of raw test files.

        Candidates are ranked by changed-file names and exact changed paths.
        Contents are decoded as UTF-8 with replacement for invalid bytes.

        Args:
            pull_request: Metadata specifying the head commit and source project.
            limit: Positive maximum number of candidate files to retrieve.
            preferred_paths: Observed caller files to prioritize within the limit.

        Returns:
            Retrieved files in rank order and the total candidate count.

        Raises:
            RemoteError: API retrieval or JSON decoding fails.
            KeyError: Required metadata is absent from the API response.
        """
        project = pull_request.head_repository or self.api.project
        ref = pull_request.head_ref
        query = urlencode({"recursive": "true", "ref": ref})
        entries = self.api.pages(f"/repository/tree?{query}", project)
        changed_paths = tuple(file.path for file in pull_request.files)
        candidates = [
            entry for entry in entries if entry["type"] == "blob"
            and (_is_test_path(entry["path"]) or entry["path"] in preferred_paths)
            and (self.suffix is None or entry["path"].endswith(self.suffix))
        ]
        candidates = _select_candidates(candidates, changed_paths, preferred_paths)
        tests: list[ExistingTest] = []
        for entry in candidates[:limit]:
            path = quote(entry["path"], safe="")
            response = self.api.client.get(
                f"{self.api.root(project)}/repository/files/{path}/raw?{urlencode({'ref': ref})}",
                self.api.headers,
            )
            tests.append(ExistingTest(entry["path"], response.body.decode("utf-8", errors="replace")))
        return tuple(tests), len(candidates)
