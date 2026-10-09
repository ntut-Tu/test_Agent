"""Intersect coverage with added diff lines."""

from __future__ import annotations

import re

from codebase_analysis.models.coverage import (
    CoverageMatch,
    CoverageReport,
    UncoveredLine,
)
from codebase_analysis.models.pull_request import ChangedFile

_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")

def added_lines(patch: str | None) -> set[int]:
    """Extract added line numbers from a unified diff.

    Args:
        patch: Diff text for one file, or None when unavailable.

    Returns:
        One-based line numbers on the new side; empty when no additions
        can be extracted from the supplied patch.
    """
    if not patch:
        return set()
    result: set[int] = set()
    line_number: int | None = None
    for line in patch.splitlines():
        match = _HUNK.match(line)
        if match:
            line_number = int(match.group(1))
        elif line_number is not None:
            if line.startswith("+"):
                result.add(line_number)
                line_number += 1
            elif line.startswith(" "):
                line_number += 1
            elif not line.startswith(("-", "\\")):
                line_number = None
    return result


def match_coverage(report: CoverageReport, changed_files: tuple[ChangedFile, ...]) -> CoverageMatch:
    """Intersect coverage with new-side diff lines after resolving source paths.

    Args:
        report: Coverage normalized by the source adapter.
        changed_files: PR/MR files, including any available patches.

    Returns:
        Uncovered changed lines, observed counts and missing-data diagnostics.
        Removed files are skipped; ambiguous suffix matches are reported
        rather than selected. Missing diffs are never treated as whole-file patches.
    """
    coverage = {file.path: file for file in report.files}
    results: list[UncoveredLine] = []
    unmatched: list[str] = []
    missing_patches: list[str] = []
    executable_count = 0
    covered_count = 0
    for changed in changed_files:
        if changed.status == "removed":
            continue
        exact = coverage.get(changed.path)
        maven_path = ("/" + changed.path).replace("/src/main/java/", "/").lstrip("/")
        if exact is None:
            exact = coverage.get(maven_path)
        if exact is not None:
            matched_file = exact
        else:
            matches = [
                file for path, file in coverage.items()
                if any(candidate.endswith("/" + path) or path.endswith("/" + candidate) for candidate in (changed.path, maven_path))
            ]
            if len(matches) != 1:
                unmatched.append(changed.path)
                continue
            matched_file = matches[0]
        if changed.patch is None:
            missing_patches.append(changed.path)
            continue
        additions = added_lines(changed.patch)
        line_numbers = matched_file.uncovered_numbers & additions
        executable = (matched_file.executable_numbers | matched_file.uncovered_numbers) & additions
        executable_count += len(executable)
        covered_count += len(executable - line_numbers)
        results.extend(
            UncoveredLine(changed.path, number, True)
            for number in sorted(line_numbers)
        )
    return CoverageMatch(
        tuple(results), tuple(unmatched), tuple(missing_patches),
        executable_count, covered_count,
    )
