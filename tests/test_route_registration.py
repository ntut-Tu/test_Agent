"""Verify shared-proxy mount preservation and rollback without a Docker daemon."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import register_traefik_route as routes


class RouteRegistrationTests(unittest.TestCase):
    def test_registration_preserves_pdd_mount_and_rolls_back_failed_start(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'dynamic').mkdir()
            (root / 'traefik.yaml').write_text('providers:\n  file:\n    directory: /etc/traefik/dynamic\n')
            current = {
                'Id': 'old', 'Config': {'Image': 'traefik:v3.6', 'Labels': {'existing': 'label'}},
                'HostConfig': {'Mounts': [{'Type': 'bind', 'Source': directory, 'Target': '/etc/traefik', 'ReadOnly': True}],
                               'PortBindings': {'80/tcp': [{'HostPort': '18487'}]}},
                'Mounts': [{'Type': 'bind', 'Source': directory, 'Destination': '/etc/traefik'}],
                'NetworkSettings': {'Networks': {'pdd-network': {'Aliases': []}}},
            }
            calls = []
            class Api:
                def call(self, method, path, payload=None):
                    calls.append((method, path, payload))
                    if path.endswith('/json') and path != '/containers/json?all=true': return current
                    if path == '/containers/json?all=true': return []
                    if path.startswith('/containers/create'):
                        self.payload = payload
                        return {'Id': 'new'}
                    if path == '/containers/new/start': raise RuntimeError('simulated start failure')
            api = Api()
            with patch.object(routes, 'DockerApi', return_value=api), self.assertRaises(RuntimeError):
                routes.register('test', 'pdd-traefik')
            self.assertEqual(api.payload['HostConfig']['Mounts'][0], current['HostConfig']['Mounts'][0])
            self.assertEqual(api.payload['HostConfig']['Mounts'][1]['Source'], str(routes.ROOT / 'deploy/traefik'))
            self.assertEqual(api.payload['Labels'], {'existing': 'label'})
            self.assertIn(('DELETE', '/containers/new?force=true', None), calls)
            self.assertEqual(calls[-1], ('POST', '/containers/old/start', None))
            self.assertEqual(list((root / 'dynamic/test-agent').iterdir()), [])

    def test_existing_mount_only_requests_reload(self):
        calls = []
        class Api:
            def call(self, method, path, payload=None):
                calls.append((method, path))
                if method == 'GET':
                    return {'Id': 'proxy', 'Mounts': [{'Destination': routes.TARGET,
                        'Source': str(routes.ROOT / 'deploy/traefik'), 'RW': False}]}
        with patch.object(routes, 'DockerApi', return_value=Api()):
            routes.register('test', 'pdd-traefik')
        self.assertEqual(calls[-1], ('POST', '/containers/proxy/kill?signal=SIGHUP'))
        self.assertEqual(len(calls), 2)
