"""Verify durable graph execution and recovery against the public behavior."""

import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from codebase_analysis.repositories.checkpoints import open_checkpoints
from codebase_analysis.repositories.sqlite import SqliteJobStore
from codebase_analysis.workflow import (
    AnalysisNodeError,
    CodebaseAnalysisAgent,
    IncompatibleCheckpointError,
)
from tests.recovery_fixtures import BUILD, CountingModel, bound_collector, changed_head


class WorkflowRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'checkpoints.sqlite3'
        self.calls = []
        self.thread = BUILD.identity + ':0'

    def invoke(self, *, resume=False, model=None, evidence=None, version='test-v1', fingerprint='config-a', thread=None):
        with open_checkpoints(self.path) as saver:
            agent = CodebaseAnalysisAgent(evidence or bound_collector(), model or CountingModel(self.calls),
                                          checkpointer=saver, workflow_version=version,
                                          configuration_fingerprint=fingerprint)
            return agent.run(1, build=BUILD, thread_id=thread or self.thread, resume=resume)

    def fail_after_coverage(self):
        with self.assertRaises(AnalysisNodeError):
            self.invoke(model=CountingModel(self.calls, fail='tests'))

    def test_reopen_resumes_saved_model_outputs_and_keeps_result_contract(self):
        self.fail_after_coverage()
        evidence = bound_collector()
        evidence.run = Mock(side_effect=AssertionError('must not recollect'))
        result = self.invoke(resume=True, evidence=evidence)
        self.assertEqual(self.calls, ['summary', 'coverage', 'tests', 'tests'])
        self.assertEqual(result.findings.pr_summary, 'summary')
        self.assertEqual(result.findings.uncovered_line_analysis[0].number, 5)
        self.assertEqual(result.findings.existing_tests[0].evidence, 'dynamic')

    def test_new_generation_reexecutes_all_operations(self):
        self.fail_after_coverage()
        self.invoke(thread=BUILD.identity + ':1')
        self.assertEqual(self.calls, ['summary', 'coverage', 'tests'] * 2)

    def test_changed_contract_or_settings_rejected_before_model_or_source(self):
        self.fail_after_coverage()
        for options in ({'version': 'test-v2'}, {'fingerprint': 'config-b'}):
            evidence = Mock()
            with self.subTest(options=options), self.assertRaises(IncompatibleCheckpointError):
                self.invoke(resume=True, evidence=evidence, **options)
            self.assertEqual(evidence.mock_calls, [])
        self.assertEqual(self.calls, ['summary', 'coverage', 'tests'])

    def test_stale_head_rejected_before_resumed_model_call(self):
        self.fail_after_coverage()
        evidence = bound_collector()
        changed_head(evidence)
        with self.assertRaisesRegex(ValueError, 'PR head changed'):
            self.invoke(resume=True, evidence=evidence)
        self.assertEqual(self.calls, ['summary', 'coverage', 'tests'])

    def test_changed_build_identity_rejected(self):
        from dataclasses import replace
        self.fail_after_coverage()
        with open_checkpoints(self.path) as saver:
            agent = CodebaseAnalysisAgent(bound_collector(), CountingModel(self.calls), checkpointer=saver,
                                          workflow_version='test-v1', configuration_fingerprint='config-a')
            with self.assertRaises(IncompatibleCheckpointError):
                agent.run(1, build=replace(BUILD, build_number=2), thread_id=self.thread, resume=True)
        self.assertEqual(self.calls, ['summary', 'coverage', 'tests'])

    def test_completed_graph_result_can_be_recovered_without_model_calls(self):
        result = self.invoke()
        again = self.invoke(resume=True, model=Mock())
        self.assertEqual(result, again)
        self.assertEqual(self.calls, ['summary', 'coverage', 'tests'])
        with self.assertRaisesRegex(ValueError, 'Thread already exists'):
            self.invoke()

    def test_resume_without_initial_checkpoint_starts_collection(self):
        self.invoke(resume=True)
        self.assertEqual(self.calls, ['summary', 'coverage', 'tests'])

    def test_provider_error_text_not_persisted(self):
        self.fail_after_coverage()
        for path in self.path.parent.glob('checkpoints.sqlite3*'):
            self.assertNotIn(b'must-not-be-persisted', path.read_bytes())
        with sqlite3.connect(self.path) as db:
            errors = db.execute("SELECT value FROM writes WHERE channel='__error__'").fetchall()
        self.assertTrue(errors)
        self.assertTrue(any(b'RuntimeError' in row[0] for row in errors))

    def test_process_death_and_worker_startup_recover_from_disk(self):
        command = [sys.executable, '-m', 'tests.recovery_process', self.temp.name]
        first = subprocess.run([*command, 'crash'], capture_output=True, text=True, timeout=20)
        self.assertEqual(first.returncode, 17, first.stderr)
        store = SqliteJobStore(Path(self.temp.name) / 'jobs.sqlite3')
        self.assertEqual(store.get(BUILD.identity).status, 'running')
        second = subprocess.run([*command, 'recover'], capture_output=True, text=True, timeout=20)
        self.assertEqual(second.returncode, 0, second.stderr)
        result = store.get(BUILD.identity)
        self.assertEqual(result.status, 'succeeded')
        self.assertEqual(result.generation, 0)
        self.assertEqual(result.execution_mode, 'resume')
        calls = [json.loads(line) for line in (Path(self.temp.name) / 'calls.jsonl').read_text().splitlines()]
        self.assertEqual(calls, ['summary', 'coverage', 'tests', 'tests'])
