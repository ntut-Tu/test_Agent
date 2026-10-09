"""Build bounded pull request context shared by analysis nodes."""

from __future__ import annotations

from dataclasses import asdict

from codebase_analysis.models.analysis import AnalysisResult


def _pr_data(context: AnalysisResult) -> dict:
    pr = context.pull_request
    return {
        "number": pr.number,
        "title": pr.title,
        "description": pr.description[:8000],
        "description_truncated": len(pr.description) > 8000,
        "url": pr.url,
        "changed_files_total": len(pr.files),
        "changed_files_omitted": max(0, len(pr.files) - 30),
        "changed_files": [
            {
                **asdict(file),
                "patch": file.patch[:2000] if file.patch else None,
                "patch_truncated": bool(file.patch and len(file.patch) > 2000),
            }
            for file in pr.files[:30]
        ],
    }
