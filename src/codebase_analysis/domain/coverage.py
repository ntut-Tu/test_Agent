"""Match normalized coverage to changed paths and added diff lines."""

from __future__ import annotations

import re
from dataclasses import dataclass

from codebase_analysis.domain.models import ChangedFile, CoverageReport, UncoveredLine
from codebase_analysis.domain.trace import TraceReport

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


@dataclass(frozen=True)
class CoverageMatch:
    """Result of matching coverage paths to changed files.

    Attributes:
        uncovered_lines: Matched lines with their added-line markers.
        unmatched_paths: Non-removed changed paths with missing or ambiguous
            coverage matches. Fully covered matched files are not included.
        missing_patch_paths: Files whose diff was unavailable; coverage cannot
            be restricted to their changed lines.
        changed_executable_count: Reported executable lines added by the diff.
        covered_changed_count: Changed executable lines covered by the tests.
    """

    uncovered_lines: tuple[UncoveredLine, ...]
    unmatched_paths: tuple[str, ...]
    missing_patch_paths: tuple[str, ...] = ()
    changed_executable_count: int = 0
    covered_changed_count: int = 0


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


class CoverageBindingError(ValueError):
    """Coverage lacks provenance or belongs to different source/XML bytes."""


def verify_coverage_binding(report: CoverageReport, revision: str, trace: TraceReport | None = None) -> None:
    """Require matching source and artifact provenance before interpreting lines.

    Args:
        report: Downloaded XML and optional producer metadata.
        revision: Current PR/MR head commit used for source retrieval.
        trace: Alternative provenance from a per-test trace of the same XML.

    Raises:
        CoverageBindingError: No provenance, mismatched commit or XML digest.
    """
    if report.provenance is None and trace is None:
        raise CoverageBindingError("Configure jenkins.metadata_url or jenkins.trace_url; coverage revision is unverified")
    if report.provenance is not None:
        if report.provenance.revision != revision:
            raise CoverageBindingError("Coverage revision differs from PR/MR head; select a build for the current head")
        if not report.artifact_sha256 or report.provenance.coverage_sha256 != report.artifact_sha256:
            raise CoverageBindingError("Coverage SHA-256 mismatch; select XML and metadata from the same build")
    if trace is not None:
        try:
            trace.verify(revision, report.artifact_sha256)
        except ValueError:
            raise CoverageBindingError("Trace revision or coverage SHA-256 mismatch") from None
