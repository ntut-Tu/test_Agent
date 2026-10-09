"""Coverage evidence and matching results."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FileCoverage:
    """Coverage for a source file, including files with no uncovered lines.

    Attributes:
        path: Source path as recorded in the coverage report.
        uncovered_numbers: One-based line numbers classified as uncovered.
        executable_numbers: All executable line numbers present in the report.
    """

    path: str
    uncovered_numbers: frozenset[int]
    executable_numbers: frozenset[int] = frozenset()


@dataclass(frozen=True)
class CoverageProvenance:
    """CI producer's declaration binding XML bytes to the tested source.

    Attributes:
        revision: Exact tested source commit, never the pre-merge head label
            for a report produced from merged source.
        coverage_sha256: SHA-256 of the archived coverage XML.
        build_id: Jenkins job/build identifier.
        scope: Maven command and test scope used by the producer.
    """

    revision: str
    coverage_sha256: str
    build_id: str
    scope: str


@dataclass(frozen=True)
class CoverageReport:
    """Normalized coverage, independent of the remote artifact format.

    Attributes:
        files: Per-file coverage entries.
        artifact_sha256: Digest of the original XML bytes, when downloaded.
        provenance: Optional CI declaration verified before line matching.
    """

    files: tuple[FileCoverage, ...]
    artifact_sha256: str | None = None
    provenance: CoverageProvenance | None = None


@dataclass(frozen=True)
class UncoveredLine:
    """An uncovered line matched to a changed file.

    Attributes:
        path: Repository-relative changed-file path.
        number: One-based line number in the new revision.
        on_added_line: Whether the supplied patch marks this line as added.
    """

    path: str
    number: int
    on_added_line: bool


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
