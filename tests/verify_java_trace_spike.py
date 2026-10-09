"""Validate synthetic producer observations through the real Python consumer."""

import json
import sys
from hashlib import sha256
from pathlib import Path

from codebase_analysis.lib.parsers.coverage import parse_coverage
from codebase_analysis.lib.parsers.java import JavaSourceAnalyzer
from codebase_analysis.lib.parsers.trace import parse_trace
from codebase_analysis.lib.rules.context import dynamic_contexts
from codebase_analysis.models.source import FocalMethod


def verify(fixture: Path) -> None:
    """Check isolation, source mapping, coverage coexistence, and the wire contract.

    Args:
        fixture: Maven fixture module containing source and completed build outputs.

    Returns:
        None. Verification reads producer outputs without modifying them.

    Raises:
        AssertionError: Any expected observation or isolation property is missing.
        ValueError: The produced trace fails consumer validation.
    """
    raw = json.loads((fixture / 'target/trace-observations.json').read_text())
    diagnostics = raw['diagnostics']
    assert diagnostics['agent_attached'], 'The Java agent did not attach'
    assert not diagnostics['errors'], diagnostics['errors']
    assert diagnostics['unattributed_calls'] > 0, 'Untagged calls were not exercised'
    xml = (fixture / 'target/site/jacoco/jacoco.xml').read_bytes()
    coverage = parse_coverage(xml)
    assert coverage.files and any(f.executable_numbers - f.uncovered_numbers for f in coverage.files)
    print('[PASS] JaCoCo produced executable-line coverage alongside trace instrumentation')

    output = fixture / 'target/java-test-trace.json'
    trace = parse_trace(output.read_bytes())
    assert trace.revision == '0' * 40, 'Expected synthetic fixture revision'
    assert trace.build_id == 'local-java-trace-spike'
    assert trace.complete is False
    trace.verify('0' * 40, sha256(xml).hexdigest())
    invocations = {invocation.test.name: invocation for invocation in trace.tests}
    assert len(trace.tests) == len(invocations) == 3
    assert set(invocations) == {'directMethod', 'firstRequest', 'secondRequest'}
    analyzer = JavaSourceAnalyzer()
    paths = {reference.path for invocation in trace.tests for reference in (invocation.test, *invocation.calls)}
    parsed = {path: analyzer.parse(path, (fixture / path).read_text()) for path in paths}
    for invocation in trace.tests:
        for reference in (invocation.test, *invocation.calls):
            matches = [method for method in parsed[reference.path] if reference.matches(method)]
            assert len(matches) == 1, f'Non-unique or missing source mapping: {reference}'

    def service_calls(test_name: str) -> set[str]:
        return {call.name for call in invocations[test_name].calls if call.class_name.endswith('.WorkService')}

    assert service_calls('directMethod') == {'calculate'}
    direct = next(call for call in invocations['directMethod'].calls if call.name == 'calculate')
    method = next(method for method in parsed[direct.path] if direct.matches(method))
    assert method.parameters == '(int value)', 'Wrong overload attributed'
    print('[PASS] Plain JUnit call maps to the correct source method and overload')
    assert service_calls('firstRequest') == {'first', 'rendezvous'}
    assert service_calls('secondRequest') == {'second', 'rendezvous'}
    for name, endpoint in [('firstRequest', 'first'), ('secondRequest', 'second')]:
        assert any(call.class_name.endswith('.WorkController') and call.name == endpoint for call in invocations[name].calls)
    print('[PASS] Concurrent RANDOM_PORT HTTP tests retain separate controller/service calls')
    assert all(call.name != 'background' for invocation in trace.tests for call in invocation.calls)
    print('[PASS] Untagged background request is not attributed to either active test')

    service_methods = [method for methods in parsed.values() for method in methods if method.class_name.endswith('.WorkService')]
    test_methods = tuple(method for methods in parsed.values() for method in methods if method.is_test)
    # Empty missing-line lists: this checks association, not a claim of missing coverage.
    contexts = dynamic_contexts(tuple(FocalMethod(method, ()) for method in service_methods), test_methods, trace)
    focal_ids = {method.identity: method.name for method in service_methods}
    pairs = {(context.test.name, focal_ids[context.focal_id]) for context in contexts}
    assert pairs == {
        ('directMethod', 'calculate'), ('firstRequest', 'first'), ('firstRequest', 'rendezvous'),
        ('secondRequest', 'second'), ('secondRequest', 'rendezvous'),
    }
    print('[PASS] Existing Python trace parser, SHA binding, and dynamic_contexts accept the producer output')
    print(f'[PASS] Read-only consumer verification completed: {output}; complete=false')


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('Usage: verify_java_trace_spike.py <producer-fixture-directory>')
    verify(Path(sys.argv[1]).resolve())
