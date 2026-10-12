"""Require collected evidence to match the submitted immutable CI identity."""

from codebase_analysis.models.analysis import AnalysisResult
from codebase_analysis.models.task import BuildRequest


def verify_build(context: AnalysisResult, build: BuildRequest | None) -> None:
    """Reject source or artifact build mismatches before model invocation."""
    if build is None:
        return
    if context.pull_request.head_ref != build.head_sha:
        raise ValueError("PR head changed since the submitted build")
    if context.coverage_provenance is None or context.coverage_provenance.build_id != build.build_id:
        raise ValueError("Coverage belongs to a different build")
    if context.trace is None or context.trace.build_id != build.build_id:
        raise ValueError("Trace belongs to a different build")
