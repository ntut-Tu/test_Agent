"""Normalize code-host response objects into shared pull request models."""

from codebase_analysis.models.pull_request import ChangedFile, PullRequest


def parse_github_pr(number: int, data: dict, changes: list[dict], repository: str) -> PullRequest:
    """Normalize github metadata and diffs without remote access."""
    files = tuple(
        ChangedFile(
            path=item["filename"],
            status=item["status"],
            patch=item.get("patch"),
            previous_path=item.get("previous_filename"),
        )
        for item in changes
    )
    return PullRequest(
        number=number,
        title=data["title"],
        description=data.get("body") or "",
        url=data["html_url"],
        head_ref=data["head"]["sha"],
        base_ref=data["base"]["sha"],
        files=files,
        head_repository=(data["head"].get("repo") or {}).get("full_name") or repository,
    )


def parse_gitlab_pr(number: int, data: dict, changes: list[dict], repository: str) -> PullRequest:
    """Normalize gitlab metadata and diffs without remote access."""
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
        head_repository=str(data.get("source_project_id") or repository),
    )
