"""Read GitHub PR and GitLab MR metadata into shared domain models."""

from __future__ import annotations

from codebase_analysis.lib.clients.github import GitHubApi
from codebase_analysis.lib.clients.gitlab import GitLabApi
from codebase_analysis.lib.parsers.pull_request import parse_github_pr, parse_gitlab_pr
from codebase_analysis.models.pull_request import PullRequest


class GitHubPrFetcher:
    """Retrieve metadata and changed files for a GitHub pull request."""

    def __init__(self, api: GitHubApi) -> None:
        """Configure the code host connection.

        Args:
            api: API client for the repository containing the PR.
        """
        self.api = api

    def fetch(self, number: int) -> PullRequest:
        """Retrieve and normalize one pull request.

        Args:
            number: Repository-scoped PR number.

        Returns:
            Metadata, changed files, commit SHAs, and the source repository.

        Raises:
            RemoteError: Retrieval fails or the file list reaches GitHub's
                3,000-file limit, making completeness uncertain.
            KeyError: Required metadata is absent from the API response.
        """
        data, changes = self.api.pull_request(number)
        return parse_github_pr(number, data, changes, self.api.repository)


class GitLabMrFetcher:
    """Retrieve metadata and diffs for a GitLab merge request."""

    def __init__(self, api: GitLabApi) -> None:
        """Configure the code host connection.

        Args:
            api: API client for the project containing the MR.
        """
        self.api = api

    def fetch(self, number: int) -> PullRequest:
        """Retrieve and normalize one merge request.

        Args:
            number: Project-scoped MR IID, not its global database ID.

        Returns:
            Metadata, changed files, commit SHAs, and the source project.

        Raises:
            RemoteError: Retrieval fails or a diff is marked collapsed or too large.
            KeyError: Required metadata is absent from the API response.
        """
        data, changes = self.api.pull_request(number)
        return parse_gitlab_pr(number, data, changes, self.api.project)
