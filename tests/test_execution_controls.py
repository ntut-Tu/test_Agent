"""Check queue migration and HTTP resume/restart behavior without remote calls."""

import json
import sqlite3
import tempfile
import time
import unittest
from dataclasses import asdict, replace
from pathlib import Path
from threading import Event
from unittest.mock import patch

from fastapi.testclient import TestClient

from codebase_analysis.bootstrap import analysis_fingerprint
from codebase_analysis.repositories.sqlite import SqliteJobStore
from codebase_analysis.server import create_app
from codebase_analysis.settings import Settings
from codebase_analysis.workflow import CodebaseAnalysisAgent
from tests.recovery_fixtures import BUILD, CountingModel, bound_collector


class ExecutionControlTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.settings = Settings.model_validate({
            'llm': {'provider': 'test', 'model': 'test'},
            'code_host': {'provider': BUILD.provider, 'repository': BUILD.repository},
            'jenkins': {'base_url': 'http://jenkins:8080', 'job_name': BUILD.job_name},
            'service': {'api_token': 'secret' * 8, 'data_directory': self.temp.name},
        })
        self.headers = {'Authorization': 'Bearer ' + 'secret' * 8}

    def wait_for(self, client, identity, expected):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            status = client.get(f'/analyses/{identity}', headers=self.headers).json()
            if status['status'] == expected:
                return status
            time.sleep(0.02)
        self.fail(f'Expected {expected}; got {status}')

    def test_http_retry_continues_and_restart_uses_new_generation(self):
        calls = []
        fail = [True]

        def factory(settings, *, checkpointer):
            model = CountingModel(calls, fail='tests' if fail[0] else None)
            return CodebaseAnalysisAgent(bound_collector(), model, checkpointer=checkpointer,
                                          configuration_fingerprint=analysis_fingerprint(settings))

        with patch('codebase_analysis.server.build_agent', side_effect=factory):
            with TestClient(create_app(self.settings)) as client:
                receipt = client.post('/analyses', json=asdict(BUILD), headers=self.headers)
                identity = receipt.json()['id']
                failed = self.wait_for(client, identity, 'failed')
                self.assertEqual((failed['generation'], failed['execution_mode']), (0, 'new'))
                self.assertNotIn('must-not-be-persisted', json.dumps(failed))
                for path in self.directory.glob('checkpoints.sqlite3*'):
                    contents = path.read_bytes()
                    self.assertNotIn(b'must-not-be-persisted', contents)
                    self.assertNotIn(('secret' * 8).encode(), contents)
            fail[0] = False
            # New application instance, same data volume. Failed jobs are not auto-retried.
            with TestClient(create_app(self.settings)) as client:
                self.assertEqual(client.get(f'/analyses/{identity}', headers=self.headers).json()['status'], 'failed')
                self.assertEqual(client.post(f'/analyses/{identity}/retry').status_code, 401)
                retry = client.post(f'/analyses/{identity}/retry', headers=self.headers)
                self.assertEqual(retry.status_code, 202)
                self.assertEqual(retry.json()['execution_mode'], 'resume')
                resumed = self.wait_for(client, identity, 'succeeded')
                self.assertEqual(calls, ['summary', 'coverage', 'tests', 'tests'])
                self.assertEqual(resumed['generation'], 0)
                again = client.post('/analyses', json=asdict(BUILD), headers=self.headers)
                self.assertEqual(again.json()['generation'], 0)
                self.assertEqual(again.status_code, 200)
                self.assertEqual(client.post(f'/analyses/{identity}/restart').status_code, 401)
                restarted = client.post(f'/analyses/{identity}/restart', headers=self.headers)
                self.assertEqual((restarted.status_code, restarted.json()['generation']), (202, 1))
                self.assertEqual(restarted.json()['execution_mode'], 'new')
                self.assertNotEqual(restarted.json()['thread_id'], resumed['thread_id'])
                self.wait_for(client, identity, 'succeeded')
                self.assertEqual(calls[-3:], ['summary', 'coverage', 'tests'])
                self.assertEqual(len(calls), 7)
                self.assertEqual(client.post('/analyses/missing/restart', headers=self.headers).status_code, 404)

    def test_active_restart_conflicts_and_does_not_run_twice(self):
        started, release = Event(), Event()

        def analyze(build):
            started.set()
            release.wait(5)
            raise RuntimeError('test failure')

        with TestClient(create_app(self.settings, analyze=analyze)) as client:
            try:
                identity = client.post('/analyses', json=asdict(BUILD), headers=self.headers).json()['id']
                self.assertTrue(started.wait(3))
                self.assertEqual(client.post(f'/analyses/{identity}/restart', headers=self.headers).status_code, 409)
                retry = client.post(f'/analyses/{identity}/retry', headers=self.headers).json()
                self.assertEqual((retry['status'], retry['generation']), ('running', 0))
            finally:
                release.set()

    def test_old_database_migrates_without_losing_successful_result(self):
        path = self.directory / 'jobs.sqlite3'
        with sqlite3.connect(path) as db:
            db.execute('''CREATE TABLE jobs (id TEXT PRIMARY KEY, request TEXT NOT NULL,
                       status TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                       result TEXT, error TEXT)''')
            db.execute('INSERT INTO jobs VALUES (?,?,?,?,?,?,?)', (
                BUILD.identity, json.dumps(asdict(BUILD)), 'succeeded', 'before', 'before',
                json.dumps({'saved': 'result'}), None))
        store = SqliteJobStore(path)
        old = store.submit(BUILD)
        self.assertEqual((old.status, old.result, old.generation), ('succeeded', {'saved': 'result'}, 0))
        self.assertEqual(old.created_at, 'before')
        self.assertEqual(store.retry(old.id).status, 'succeeded')
        new = store.restart(old.id)
        self.assertEqual((new.id, new.generation, new.result), (old.id, 1, None))
        self.assertEqual(SqliteJobStore(path).get(old.id).generation, 1)

    def test_restart_and_retry_enforce_capacity_and_recovery_preserves_failures(self):
        store = SqliteJobStore(self.directory / 'jobs.sqlite3', max_pending=1)
        first = store.submit(BUILD)
        store.claim()
        store.finish(first.id, None, 'TestFailure')
        second = store.submit(replace(BUILD, build_number=2))
        for operation in (store.retry, store.restart):
            with self.assertRaises(OverflowError):
                operation(first.id)
        store.claim()
        store.recover_running()
        self.assertEqual(store.get(first.id).status, 'failed')
        self.assertEqual(store.get(second.id).execution_mode, 'resume')
        self.assertEqual(store.get(second.id).generation, 0)
        self.assertEqual(store.get(second.id).status, 'queued')

    def test_fingerprint_changes_with_prompts_model_and_collection_but_not_credentials(self):
        fingerprint = analysis_fingerprint(self.settings)
        for section, key, value in [('llm', 'model', 'other'), ('llm', 'options', {'temperature': 0}),
                                    ('analysis', 'max_test_files', 2)]:
            data = self.settings.model_dump(mode='json')
            data[section][key] = value
            self.assertNotEqual(analysis_fingerprint(Settings.model_validate(data)), fingerprint)
        data = self.settings.model_dump(mode='json')
        data['llm']['api_key'] = 'changed-key'
        data['code_host']['token'] = 'changed-token'
        data['jenkins'].update(username='operator', api_token='changed-token')
        self.assertEqual(analysis_fingerprint(Settings.model_validate(data)), fingerprint)
        with patch('codebase_analysis.bootstrap.pr.INSTRUCTIONS', 'changed prompt'):
            self.assertNotEqual(analysis_fingerprint(self.settings), fingerprint)
