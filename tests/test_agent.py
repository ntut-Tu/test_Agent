import unittest

from codebase_analysis.application.agent import CodebaseAnalysis, CodebaseAnalysisAgent
from codebase_analysis.domain.models import (
    ChangedFile,
    ExistingTest,
    LineFinding,
    PullRequest,
)
from codebase_analysis.domain.validation import InvalidFindingsError
from tests.fakes import StubCoverage, StubPrFetcher, StubTestRetriever


class AgentTests(unittest.TestCase):
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
