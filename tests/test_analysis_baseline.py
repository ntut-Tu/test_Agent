"""Compare synthetic evidence, prompts, schemas and results to the saved baseline."""

import json
import unittest
from dataclasses import asdict
from pathlib import Path

from codebase_analysis.lib.clients.langchain import LangChainClient
from codebase_analysis.nodes.analysis import AnalysisNodes
from codebase_analysis.workflow import CodebaseAnalysisAgent
from tests.java_fixtures import SOURCE_PATH, collector


class RecordingChat:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def with_structured_output(self, schema):
        self.schema = schema
        return self

    def invoke(self, messages):
        self.calls.append({"schema": self.schema.model_json_schema(), "messages": messages})
        return next(self.responses)


class AnalysisBaselineTests(unittest.TestCase):
    def test_collected_evidence_and_model_contract_match_pre_refactor_baseline(self):
        context = collector().run(1)
        chat = RecordingChat([
            {"summary": "PR summary"},
            {"lines": [{"path": SOURCE_PATH, "number": 5, "reason": "express branch"}]},
            {"selections": [{
                "focal_id": context.focal_methods[0].method.identity,
                "test_id": context.test_methods[0].identity,
                "reason": "reuse Spring setup",
            }]},
        ])
        model = AnalysisNodes(LangChainClient(chat))
        result = {
            "summary": model.summarize_pr(context),
            "lines": [asdict(item) for item in model.identify_uncovered_lines(context)],
            "tests": [asdict(item) for item in model.select_existing_tests(context)],
        }
        actual = {"context": asdict(context), "calls": chat.calls, "result": result}
        expected = (Path(__file__).parent / "fixtures" / "analysis_before_refactor.json").read_text()
        self.assertEqual(json.dumps(actual, ensure_ascii=False, sort_keys=True, indent=2) + "\n", expected)

    def test_graph_preserves_original_model_messages_schemas_and_results(self):
        expected = json.loads((Path(__file__).parent / 'fixtures' / 'analysis_before_refactor.json').read_text())
        evidence = collector()
        context = evidence.run(1)
        chat = RecordingChat([
            {'summary': expected['result']['summary']},
            {'lines': expected['result']['lines']},
            {'selections': [{
                'focal_id': context.focal_methods[0].method.identity,
                'test_id': context.test_methods[0].identity,
                'reason': 'reuse Spring setup',
            }]},
        ])
        result = CodebaseAnalysisAgent(evidence, AnalysisNodes(LangChainClient(chat))).run(1)
        actual = {'context': asdict(result.context), 'calls': chat.calls, 'result': {
            'summary': result.findings.pr_summary,
            'lines': [asdict(item) for item in result.findings.uncovered_line_analysis],
            'tests': [asdict(item) for item in result.findings.existing_tests],
        }}
        self.assertEqual(json.loads(json.dumps(actual)), expected)
