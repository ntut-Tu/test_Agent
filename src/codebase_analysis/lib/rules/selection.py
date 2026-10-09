"""Rank candidate tests using paths and observed callers."""

from __future__ import annotations

from codebase_analysis.lib.rules.paths import is_java_test_path


def is_test_path(path: str) -> bool:
    """Classify likely test files using existing path and filename conventions."""
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


def select_candidates(entries: list[dict], changed_paths: tuple[str, ...], preferred: tuple[str, ...]) -> list[dict]:
    """Prefer observed callers and changed tests, then rank filename relevance.

    Returns:
        A new sorted candidate list; the input entries are not mutated.
    """
    changed_tests = [item for item in entries if item["path"] in changed_paths]
    candidates = [item for item in entries if item["path"] in preferred or not changed_tests or item in changed_tests]
    candidates.sort(key=lambda item: (item["path"] not in preferred, _test_score(item["path"], changed_paths)))
    return candidates
