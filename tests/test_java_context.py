import json
import unittest
from dataclasses import replace
from types import SimpleNamespace

from codebase_analysis.domain.context import TestContext
from codebase_analysis.domain.models import LlmFindings
from codebase_analysis.domain.trace import dynamic_contexts
from codebase_analysis.domain.validation import InvalidFindingsError, validate_findings
from codebase_analysis.infrastructure.errors import RemoteError
from codebase_analysis.infrastructure.llm.langchain import LangChainAnalysisModel
from codebase_analysis.infrastructure.source.java import JavaSourceAnalyzer
from codebase_analysis.infrastructure.trace.jenkins import parse_trace
from tests.java_fixtures import (
    SOURCE,
    SOURCE_PATH,
    TEST_SOURCE,
    collector,
    trace_payload,
)
from tests.test_langchain_model import FakeChatModel


class JavaContextTests(unittest.TestCase):
    def test_coverage_maps_only_changed_missing_lines_to_java_overload(self):
        context = collector().run(1)
        self.assertEqual([line.number for line in context.uncovered_lines], [5])
        self.assertEqual(len(context.focal_methods), 1)
        focal = context.focal_methods[0]
        self.assertEqual(focal.method.parameters, "(int amount, boolean express)")
        self.assertIn("return 100; // UNCOVERED", focal.annotated_source())
        self.assertIn("@SpringBootTest", context.test_methods[0].file_context)
        self.assertEqual(context.test_methods[0].file_context, TEST_SOURCE)

    def test_trace_supplies_observed_test_without_llm_selection(self):
        trace = parse_trace(json.dumps(trace_payload()).encode())
        context = collector(SimpleNamespace(fetch=lambda: trace)).run(1)
        model = FakeChatModel([])
        selected = LangChainAnalysisModel(model).select_existing_tests(context)
        self.assertEqual(model.schemas, [])
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0].evidence, "dynamic")
        self.assertEqual(selected[0].test.name, "regularShipping")
        self.assertEqual(selected[0].test.file_context, TEST_SOURCE)
        validate_findings(context, LlmFindings("", (), selected))

    def test_trace_for_other_overload_does_not_prove_target_invocation(self):
        payload = trace_payload()
        payload["tests"][0]["calls"][0]["line"] = 9
        trace = parse_trace(json.dumps(payload).encode())
        context = collector(SimpleNamespace(fetch=lambda: trace)).run(1)
        self.assertEqual(context.dynamic_test_contexts, ())

    def test_calls_remain_bound_to_test_identity(self):
        payload = trace_payload()
        other = {**payload["tests"][0]["test"], "name": "unretrievedTest"}
        payload["tests"] = [
            {"test": payload["tests"][0]["test"], "calls": []},
            {"test": other, "calls": payload["tests"][0]["calls"]},
        ]
        context = collector().run(1)
        trace = parse_trace(json.dumps(payload).encode())
        self.assertEqual(dynamic_contexts(context.focal_methods, context.test_methods, trace), ())

    def test_mismatched_revision_or_coverage_digest_fails_closed(self):
        for field, value in [("revision", "b" * 40), ("coverage_sha256", "0" * 64)]:
            payload = trace_payload()
            payload[field] = value
            trace = parse_trace(json.dumps(payload).encode())
            with self.subTest(field=field), self.assertRaises(ValueError):
                collector(SimpleNamespace(fetch=lambda: trace)).run(1)

    def test_invalid_trace_contract_is_rejected(self):
        for field, value in [("path", "../Secret.java"), ("line", 0), ("line", "8")]:
            payload = trace_payload()
            payload["tests"][0]["test"][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(RemoteError):
                parse_trace(json.dumps(payload).encode())
        payload = trace_payload()
        payload["schema_version"] = 2
        with self.assertRaises(RemoteError):
            parse_trace(json.dumps(payload).encode())

    def test_llm_fallback_rejects_invented_method_ids(self):
        context = collector().run(1)
        model = FakeChatModel([{"selections": [{
            "focal_id": context.focal_methods[0].method.identity,
            "test_id": "invented", "reason": "guess",
        }]}])
        with self.assertRaises(RemoteError):
            LangChainAnalysisModel(model).select_existing_tests(context)

    def test_model_cannot_claim_or_drop_dynamic_evidence(self):
        context = collector().run(1)
        invented = TestContext(context.focal_methods[0].method.identity, context.test_methods[0], "dynamic", "invented")
        with self.assertRaises(InvalidFindingsError):
            validate_findings(context, LlmFindings("", (), (invented,)))
        context = replace(context, dynamic_test_contexts=(invented,))
        with self.assertRaises(InvalidFindingsError):
            validate_findings(context, LlmFindings("", (), ()))

    def test_nested_classes_and_overloads_have_distinct_identities(self):
        source = SOURCE.replace("\n}", "\n    class Nested { int fee() { return 0; } }\n}")
        methods = JavaSourceAnalyzer().parse(SOURCE_PATH, source)
        self.assertEqual(len(methods), 3)
        self.assertEqual(len({method.identity for method in methods}), 3)
        self.assertEqual(methods[-1].class_name, "demo.ShippingService.Nested")

    def test_malformed_java_fails_instead_of_producing_partial_context(self):
        with self.assertRaises(RemoteError):
            JavaSourceAnalyzer().parse(SOURCE_PATH, "class Broken { void x(")
