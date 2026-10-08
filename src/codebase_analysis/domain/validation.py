"""Validate model references against collected evidence."""

from codebase_analysis.domain.context import TestContext
from codebase_analysis.domain.models import AnalysisResult, LlmFindings


class InvalidFindingsError(ValueError):
    """Analysis selected evidence that was not supplied."""


def validate_findings(context: AnalysisResult, findings: LlmFindings) -> None:
    """Ensure selected lines and tests exist in the collected candidates.

    This checks references, not the factual accuracy of generated prose.

    Args:
        context: Evidence collected for the PR/MR.
        findings: Outputs from any implementation of the analysis model.

    Raises:
        InvalidFindingsError: A selected line or test path is absent from context.
    """
    allowed_lines = {(line.path, line.number) for line in context.uncovered_lines}
    if any((line.path, line.number) not in allowed_lines for line in findings.uncovered_line_analysis):
        raise InvalidFindingsError("Analysis cited a line absent from coverage candidates")
    allowed_focals = {focal.method.identity for focal in context.focal_methods}
    allowed_tests = {test.identity: test for test in context.test_methods}
    observed = {(item.focal_id, item.test.identity): item for item in context.dynamic_test_contexts}
    for selection in findings.existing_tests:
        if not isinstance(selection, TestContext):
            raise InvalidFindingsError("Analysis must return method-level test contexts")
        if selection.focal_id not in allowed_focals or allowed_tests.get(selection.test.identity) != selection.test:
            raise InvalidFindingsError("Analysis selected an unknown focal method or test declaration")
        key = (selection.focal_id, selection.test.identity)
        if selection.evidence == "dynamic" and observed.get(key) != selection:
            raise InvalidFindingsError("Analysis claimed dynamic evidence absent from the trace")
        if selection.evidence not in {"dynamic", "llm"}:
            raise InvalidFindingsError("Analysis used an unknown evidence type")
    selected_keys = {(item.focal_id, item.test.identity) for item in findings.existing_tests if item.evidence == "dynamic"}
    if not observed.keys() <= selected_keys:
        raise InvalidFindingsError("Analysis dropped observed test contexts")
