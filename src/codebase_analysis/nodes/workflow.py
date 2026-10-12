"""Adapt collection and model operations to checkpointable graph state."""

from dataclasses import asdict

from codebase_analysis.collection import CodebaseAnalysis
from codebase_analysis.interfaces import AnalysisModel
from codebase_analysis.lib.parsers.state import parse_context, parse_result
from codebase_analysis.lib.rules.build import verify_build
from codebase_analysis.lib.rules.validation import validate_findings
from codebase_analysis.models.analysis import LineFinding, LlmFindings
from codebase_analysis.models.state import AnalysisState
from codebase_analysis.models.task import BuildRequest


class WorkflowNodes:
    """Return state updates while keeping model clients outside persisted state."""

    def __init__(self, collector: CodebaseAnalysis, model: AnalysisModel) -> None:
        self.collector = collector
        self.model = model

    def collect(self, state: AnalysisState) -> dict:
        """Collect and bind all evidence before any model operation."""
        context = self.collector.run(state['number'])
        build = BuildRequest(**state['build']) if state['build'] else None
        verify_build(context, build)
        return {'context': asdict(context)}

    def summarize_pr(self, state: AnalysisState) -> dict:
        """Persist the PR summary independently from later model operations."""
        return {'pr_summary': self.model.summarize_pr(parse_context(state['context']))}

    def analyze_coverage(self, state: AnalysisState) -> dict:
        """Preserve the existing uncovered-line operation and prompt inputs."""
        findings = self.model.identify_uncovered_lines(parse_context(state['context']))
        return {'uncovered_line_analysis': [asdict(item) for item in findings]}

    def select_tests(self, state: AnalysisState) -> dict:
        """Select test context and validate references before persisting it."""
        context = parse_context(state['context'])
        tests = self.model.select_existing_tests(context)
        findings = LlmFindings(
            state['pr_summary'],
            tuple(LineFinding(**item) for item in state['uncovered_line_analysis']),
            tests,
        )
        validate_findings(context, findings)
        return {'existing_tests': [asdict(item) for item in tests]}

    def validate(self, state: AnalysisState) -> dict:
        """Rehydrate and validate the complete result before publishing it."""
        result = parse_result({'context': state['context'], 'findings': {
            'pr_summary': state['pr_summary'],
            'uncovered_line_analysis': state['uncovered_line_analysis'],
            'existing_tests': state['existing_tests'],
        }})
        validate_findings(result.context, result.findings)
        return {'result': asdict(result)}
