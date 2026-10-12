"""Deterministic build evidence and models for persistent execution tests."""

from dataclasses import replace
from types import SimpleNamespace

from codebase_analysis.lib.parsers.trace import parse_trace
from codebase_analysis.models.analysis import LineFinding
from codebase_analysis.models.task import BuildRequest
from tests.java_fixtures import REVISION, SOURCE_PATH, collector, trace_payload

BUILD = BuildRequest('github', 'org/repo', 1, REVISION, 'job', 1)


def bound_collector():
    payload = trace_payload()
    payload['build_id'] = BUILD.build_id
    import json
    evidence = collector(SimpleNamespace(fetch=lambda: parse_trace(json.dumps(payload).encode())))
    return evidence


class CountingModel:
    def __init__(self, calls, fail=None):
        self.calls = calls
        self.fail = fail

    def record(self, operation):
        self.calls.append(operation)
        if self.fail == operation:
            raise RuntimeError('api_key=must-not-be-persisted')

    def summarize_pr(self, context):
        self.record('summary')
        return 'summary'

    def identify_uncovered_lines(self, context):
        self.record('coverage')
        return (LineFinding(SOURCE_PATH, 5, 'branch'),)

    def select_existing_tests(self, context):
        self.record('tests')
        return context.dynamic_test_contexts


def changed_head(evidence):
    current = evidence.pull_requests.fetch(BUILD.number)
    evidence.pull_requests = SimpleNamespace(fetch=lambda number: replace(current, head_ref='b' * 40))
