"""Validate source revision and coverage artifact identity."""

from __future__ import annotations

from codebase_analysis.models.coverage import CoverageReport
from codebase_analysis.models.trace import TraceReport


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
