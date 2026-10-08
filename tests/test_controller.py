"""Controller/storage contracts without external services or LLM calls."""

import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from fastapi.testclient import TestClient

from codebase_analysis.domain.jobs import BuildRequest
from codebase_analysis.infrastructure.jobs.analysis import settings_for_build
from codebase_analysis.infrastructure.jobs.sqlite import SqliteJobStore
from codebase_analysis.infrastructure.settings import Settings
from codebase_analysis.server import create_app


@dataclass
class FakeResult:
    summary: str = 'analyzed'


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.settings = Settings.model_validate({
            'llm': {'provider': 'test', 'model': 'test'},
            'code_host': {'provider': 'github', 'repository': 'org/repo'},
            'jenkins': {'base_url': 'http://jenkins:8080/ci', 'job_name': 'pdd/test-all-server'},
            'service': {'api_token': 'secret' * 8, 'data_directory': self.temp.name},
        })
        self.payload = {'provider': 'github', 'repository': 'org/repo', 'number': 31,
                        'head_sha': 'a' * 40, 'job_name': 'pdd/test-all-server', 'build_number': 9}
        self.headers = {'Authorization': 'Bearer ' + 'secret' * 8}

    def test_auth_validation_async_result_and_deduplication(self):
        calls = []
        def analyze(build):
            calls.append(build)
            return FakeResult()
        with TestClient(create_app(self.settings, analyze=analyze)) as client:
            self.assertEqual(client.get('/health/ready').status_code, 200)
            self.assertEqual(client.post('/analyses', json=self.payload).status_code, 401)
            wrong = {**self.payload, 'repository': 'other/repo'}
            self.assertEqual(client.post('/analyses', json=wrong, headers=self.headers).status_code, 422)
            extra = {**self.payload, 'artifact_url': 'http://sensitive.invalid'}
            response = client.post('/analyses', json=extra, headers=self.headers)
            self.assertEqual(response.status_code, 422)
            self.assertNotIn('sensitive.invalid', response.text)
            receipt = client.post('/analyses', json=self.payload, headers=self.headers)
            self.assertEqual(receipt.status_code, 202)
            identity = receipt.json()['id']
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                status = client.get(f'/analyses/{identity}', headers=self.headers).json()
                if status['status'] == 'succeeded':
                    break
                time.sleep(0.05)
            self.assertEqual(status['status'], 'succeeded')
            self.assertEqual(client.get(f'/analyses/{identity}/result', headers=self.headers).json(), {'summary': 'analyzed'})
            again = client.post('/test-agent/analyses', json=self.payload, headers=self.headers)
            self.assertEqual(again.json()['id'], identity)
            self.assertEqual(len(calls), 1)

    def test_build_urls_are_pinned_and_settings_are_not_mutated(self):
        one = settings_for_build(self.settings, BuildRequest(**self.payload))
        two = settings_for_build(self.settings, BuildRequest(**{**self.payload, 'build_number': 10}))
        self.assertIn('/ci/job/pdd/job/test-all-server/9/artifact/', one.jenkins.trace_url)
        self.assertIn('/10/artifact/', two.jenkins.trace_url)
        self.assertIsNone(self.settings.jenkins.trace_url)
        with self.assertRaises(ValueError):
            settings_for_build(self.settings, BuildRequest(**{**self.payload, 'job_name': '../other'}))

    def test_concurrent_submission_claims_once_and_survives_reopen(self):
        path = Path(self.temp.name) / 'jobs.sqlite3'
        store = SqliteJobStore(path)
        request = BuildRequest(**self.payload)
        with ThreadPoolExecutor(max_workers=8) as pool:
            jobs = list(pool.map(lambda _: store.submit(request), range(20)))
        self.assertEqual({job.id for job in jobs}, {request.identity})
        with ThreadPoolExecutor(max_workers=8) as pool:
            claimed = list(pool.map(lambda _: store.claim(), range(8)))
        self.assertEqual(sum(job is not None for job in claimed), 1)
        store = SqliteJobStore(path)
        store.interrupt_running()
        self.assertEqual(store.get(request.identity).error, 'Interrupted')
        store.retry(request.identity)
        self.assertEqual(store.claim().id, request.identity)
        store.finish(request.identity, {'ok': True}, None)
        self.assertEqual(store.retry(request.identity).status, 'succeeded')

    def test_queue_limit_does_not_reject_duplicate_delivery(self):
        store = SqliteJobStore(Path(self.temp.name) / 'queue.sqlite3', max_pending=1)
        request = BuildRequest(**self.payload)
        store.submit(request)
        self.assertEqual(store.submit(request).id, request.identity)
        with self.assertRaises(OverflowError):
            store.submit(BuildRequest(**{**self.payload, 'build_number': 10}))

    def test_failures_do_not_expose_exception_secrets(self):
        def fail(build):
            raise RuntimeError('api_key=do-not-expose')
        with TestClient(create_app(self.settings, analyze=fail)) as client:
            identity = client.post('/analyses', json=self.payload, headers=self.headers).json()['id']
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                response = client.get(f'/analyses/{identity}', headers=self.headers)
                if response.json()['status'] == 'failed':
                    break
                time.sleep(0.05)
            self.assertEqual(response.json()['error'], 'RuntimeError')
            self.assertNotIn('do-not-expose', response.text)
            self.assertEqual(client.get(f'/analyses/{identity}/result', headers=self.headers).status_code, 409)


if __name__ == '__main__':
    unittest.main()
