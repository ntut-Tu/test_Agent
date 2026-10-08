import unittest

from codebase_analysis.infrastructure.llm.langchain import LangChainAnalysisModel
from tests.java_fixtures import SOURCE_PATH, collector


class FakeStructuredModel:
    def __init__(self, response):
        self.response = response

    def invoke(self, messages):
        return self.response


class FakeChatModel:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.schemas = []

    def with_structured_output(self, schema):
        self.schemas.append(schema.__name__)
        return FakeStructuredModel(next(self.responses))


class LangChainModelTests(unittest.TestCase):
    def setUp(self):
        self.context = collector().run(1)

    def test_three_green_outputs_use_langchain_structured_model(self):
        fake = FakeChatModel([
            {"summary": "PR summary"},
            {"lines": [{"path": SOURCE_PATH, "number": 5, "reason": "express branch"}]},
            {"selections": [{
                "focal_id": self.context.focal_methods[0].method.identity,
                "test_id": self.context.test_methods[0].identity, "reason": "reuse Spring setup",
            }]},
        ])
        model = LangChainAnalysisModel(fake)
        self.assertEqual(model.summarize_pr(self.context), "PR summary")
        self.assertEqual(model.identify_uncovered_lines(self.context)[0].number, 5)
        selected = model.select_existing_tests(self.context)
        self.assertEqual(selected[0].test.name, "regularShipping")
        self.assertEqual(selected[0].evidence, "llm")
        self.assertIn("@SpringBootTest", selected[0].test.file_context)
        self.assertEqual(fake.schemas, ["_PrSummary", "_UncoveredLines", "_ExistingTests"])


if __name__ == "__main__":
    unittest.main()
