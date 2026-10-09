import unittest

from codebase_analysis.collection import CodebaseAnalysis
from codebase_analysis.lib.rules.validation import InvalidFindingsError
from codebase_analysis.models.analysis import LineFinding
from codebase_analysis.models.pull_request import ChangedFile, PullRequest
from codebase_analysis.models.source import ExistingTest
from codebase_analysis.workflow import CodebaseAnalysisAgent
from tests.fakes import StubCoverage, StubPrFetcher, StubTestRetriever


class AgentTests(unittest.TestCase):
    def test_build_mismatch_is_rejected_before_any_llm_call(self):
        from types import SimpleNamespace
        from unittest.mock import Mock

        from codebase_analysis.models.task import BuildRequest

        build = BuildRequest('github', 'org/repo', 31, 'a' * 40, 'pdd/test', 9)
        for head, coverage_id, trace_id in [
            ('b' * 40, 'pdd/test/9', 'pdd/test/9'),
            ('a' * 40, 'pdd/test/8', 'pdd/test/9'),
            ('a' * 40, 'pdd/test/9', 'pdd/test/8'),
        ]:
            context = SimpleNamespace(
                pull_request=SimpleNamespace(head_ref=head),
                coverage_provenance=SimpleNamespace(build_id=coverage_id),
                trace=SimpleNamespace(build_id=trace_id),
            )
            collector, model = Mock(), Mock()
            collector.run.return_value = context
            with self.subTest(head=head, coverage=coverage_id, trace=trace_id), self.assertRaises(ValueError):
                CodebaseAnalysisAgent(collector, model).run(31, build=build)
            self.assertEqual(model.mock_calls, [])

    def test_agent_runs_three_distinct_llm_steps(self):
        pr = PullRequest(1, "Fix", "", "url", "sha", "base", (ChangedFile("src/mod.py", "modified", "@@ -1 +1 @@\n-a\n+b"),))

        class Model:
            def __init__(self):
                self.calls = []

            def summarize_pr(self, context):
                self.calls.append("pr")
                return "summary"

            def identify_uncovered_lines(self, context):
                self.calls.append("coverage")
                return (LineFinding("src/mod.py", 1, "risk"),)

            def select_existing_tests(self, context):
                self.calls.append("tests")
                assert context.tests_truncated
                return ()

        tests = StubTestRetriever((ExistingTest("tests/test_mod.py", "assert True"),), 2)
        model = Model()
        result = CodebaseAnalysisAgent(CodebaseAnalysis(StubPrFetcher(pr), StubCoverage(), tests, 1), model).run(1)
        self.assertEqual(result.findings.pr_summary, "summary")
        self.assertEqual(result.findings.uncovered_line_analysis[0].number, 1)
        self.assertEqual(result.findings.existing_tests, ())
        self.assertEqual(model.calls, ["pr", "coverage", "tests"])

    def test_rejects_unsupported_findings_from_any_model_implementation(self):
        pr = PullRequest(1, "Fix", "", "url", "sha", "base", (ChangedFile("src/mod.py", "modified", None),))

        class Model:
            def __init__(self, lines, paths):
                self.lines = lines
                self.paths = paths

            def summarize_pr(self, context):
                return "summary"

            def identify_uncovered_lines(self, context):
                return self.lines

            def select_existing_tests(self, context):
                return self.paths

        collector = CodebaseAnalysis(StubPrFetcher(pr), StubCoverage(), StubTestRetriever())
        cases = [((LineFinding("src/mod.py", 99, "invented"),), ()), ((), ("tests/unknown.py",))]
        for lines, paths in cases:
            with self.subTest(lines=lines, paths=paths), self.assertRaises(InvalidFindingsError):
                CodebaseAnalysisAgent(collector, Model(lines, paths)).run(1)
