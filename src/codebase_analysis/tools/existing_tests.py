"""Collect bounded test candidates from a pinned source revision."""

from __future__ import annotations

from codebase_analysis.lib.clients.github import GitHubApi
from codebase_analysis.lib.clients.gitlab import GitLabApi
from codebase_analysis.lib.rules.selection import is_test_path, select_candidates
from codebase_analysis.models.pull_request import PullRequest
from codebase_analysis.models.source import ExistingTest


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
        entries = self.api.tree(pull_request.head_ref, repository)
        changed_paths = tuple(file.path for file in pull_request.files)
        candidates = [
            item for item in entries
            if item["type"] == "blob" and (is_test_path(item["path"]) or item["path"] in preferred_paths)
            and (self.suffix is None or item["path"].endswith(self.suffix))
        ]
        candidates = select_candidates(candidates, changed_paths, preferred_paths)
        tests: list[ExistingTest] = []
        for item in candidates[:limit]:
            tests.append(ExistingTest(item["path"], self.api.read_blob(item, repository)))
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
        entries = self.api.tree(ref, project)
        changed_paths = tuple(file.path for file in pull_request.files)
        candidates = [
            entry for entry in entries if entry["type"] == "blob"
            and (is_test_path(entry["path"]) or entry["path"] in preferred_paths)
            and (self.suffix is None or entry["path"].endswith(self.suffix))
        ]
        candidates = select_candidates(candidates, changed_paths, preferred_paths)
        tests: list[ExistingTest] = []
        for entry in candidates[:limit]:
            tests.append(ExistingTest(entry["path"], self.api.read_file(entry["path"], ref, project)))
        return tuple(tests), len(candidates)
