"""Read GitHub PR and GitLab MR metadata into shared domain models."""

from __future__ import annotations

from codebase_analysis.domain.models import ChangedFile, PullRequest
from codebase_analysis.infrastructure.code_hosts.api import GitHubApi, GitLabApi
from codebase_analysis.infrastructure.errors import RemoteError


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
        data = self.api.get(f"/pulls/{number}")
        files = tuple(
            ChangedFile(
                path=item["filename"],
                status=item["status"],
                patch=item.get("patch"),
                previous_path=item.get("previous_filename"),
            )
            for item in self.api.pages(f"/pulls/{number}/files")
        )
        if len(files) >= 3000:
            raise RemoteError("GitHub PR file listing may exceed its 3000-file API limit")
        return PullRequest(
            number=number,
            title=data["title"],
            description=data.get("body") or "",
            url=data["html_url"],
            head_ref=data["head"]["sha"],
            base_ref=data["base"]["sha"],
            files=files,
            head_repository=(data["head"].get("repo") or {}).get("full_name") or self.api.repository,
        )


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
        data = self.api.get(f"/merge_requests/{number}")
        changes = list(self.api.pages(f"/merge_requests/{number}/diffs"))
        if any(item.get("collapsed") or item.get("too_large") for item in changes):
            raise RemoteError("GitLab returned an incomplete merge request diff")
        files = tuple(
            ChangedFile(
                path=item["new_path"],
                status=("removed" if item.get("deleted_file") else "added" if item.get("new_file") else "renamed" if item.get("renamed_file") else "modified"),
                patch=item.get("diff"),
                previous_path=item["old_path"] if item.get("renamed_file") else None,
            )
            for item in changes
        )
        return PullRequest(
            number=number,
            title=data["title"],
            description=data.get("description") or "",
            url=data["web_url"],
            head_ref=data["sha"],
            base_ref=data["diff_refs"]["base_sha"],
            files=files,
            head_repository=str(data.get("source_project_id") or self.api.project),
        )
