"""Mount this project's route directory into an existing shared Traefik."""

import http.client
import json
import socket
import subprocess
from copy import deepcopy
from pathlib import Path
from urllib.parse import quote

import yaml

from codebase_analysis.settings import load_settings

ROOT = Path(__file__).resolve().parents[1]
TARGET = '/etc/traefik/dynamic/test-agent'


class UnixConnection(http.client.HTTPConnection):
    def __init__(self, path):
        super().__init__('localhost', timeout=40)
        self.socket_path = path

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self.socket_path)


class DockerApi:
    """Use the selected local engine without changing the user's Docker context."""

    def __init__(self, context):
        raw = subprocess.check_output(['docker', 'context', 'inspect', context], text=True)
        endpoint = json.loads(raw)[0]['Endpoints']['docker']['Host']
        if not endpoint.startswith('unix://'):
            raise ValueError('This local deployment helper requires a Unix Docker socket')
        self.socket_path = endpoint.removeprefix('unix://')

    def call(self, method, path, payload=None):
        connection = UnixConnection(self.socket_path)
        try:
            connection.request(method, path, body=json.dumps(payload) if payload is not None else None,
                               headers={'Content-Type': 'application/json'})
            response = connection.getresponse()
            body = response.read()
            if response.status >= 400:
                raise RuntimeError(f'Docker API {method} {path}: HTTP {response.status}')
            return json.loads(body) if body else None
        finally:
            connection.close()


def register(context: str, name: str) -> None:
    """Add one read-only route mount, preserving existing container configuration.

    The old container is retained stopped for rollback after the initial migration.
    Subsequent calls only send SIGHUP, since file-provider watches are not recursive.
    """
    api = DockerApi(context)
    current = api.call('GET', f'/containers/{quote(name, safe="")}/json')
    source = str(ROOT / 'deploy/traefik')
    existing = next((item for item in current['Mounts'] if item['Destination'] == TARGET), None)
    if existing:
        if existing['Source'] != source or existing['RW']:
            raise ValueError('Existing Agent route mount does not match this checkout')
        api.call('POST', f'/containers/{current["Id"]}/kill?signal=SIGHUP')
        print('Reloaded shared Traefik; route source remains in test_Agent')
        return
    parent = next((item for item in current['Mounts'] if item['Destination'] == '/etc/traefik' and item['Type'] == 'bind'), None)
    if parent is None:
        raise ValueError('Expected existing /etc/traefik directory bind; inspect deployment first')
    static = yaml.safe_load((Path(parent['Source']) / 'traefik.yaml').read_text())
    if static.get('providers', {}).get('file', {}).get('directory') != '/etc/traefik/dynamic':
        raise ValueError('Unexpected file-provider directory; no shared configuration changed')
    # Empty mount point only: no Agent route file is copied into the PDD project.
    (Path(parent['Source']) / 'dynamic/test-agent').mkdir(exist_ok=True)
    payload = deepcopy(current['Config'])
    payload['Hostname'] = ''
    payload['HostConfig'] = deepcopy(current['HostConfig'])
    payload['HostConfig'].setdefault('Mounts', []).append({
        'Type': 'bind', 'Source': source, 'Target': TARGET, 'ReadOnly': True,
    })
    payload['NetworkingConfig'] = {'EndpointsConfig': {
        network: {'Aliases': info.get('Aliases') or []}
        for network, info in current['NetworkSettings']['Networks'].items()
    }}
    candidate = name + '-test-agent-next'
    backup = name + '-before-test-agent'
    # Preflight name collisions before stopping the proxy.
    containers = api.call('GET', '/containers/json?all=true')
    if any('/' + n in item['Names'] for item in containers for n in (candidate, backup)):
        raise ValueError('Migration container name already exists; inspect before retrying')
    created = api.call('POST', '/containers/create?name=' + quote(candidate), payload)['Id']
    stopped = renamed = False
    try:
        api.call('POST', f'/containers/{current["Id"]}/stop?t=10')
        stopped = True
        api.call('POST', f'/containers/{current["Id"]}/rename?name={quote(backup)}')
        renamed = True
        api.call('POST', f'/containers/{created}/rename?name={quote(name)}')
        api.call('POST', f'/containers/{created}/start')
    except Exception:
        api.call('DELETE', f'/containers/{created}?force=true')
        if renamed:
            api.call('POST', f'/containers/{current["Id"]}/rename?name={quote(name)}')
        if stopped:
            api.call('POST', f'/containers/{current["Id"]}/start')
        raise
    print(f'Registered independent Agent route mount; stopped rollback container: {backup}')


def main():
    settings = load_settings(ROOT / 'values.yaml')
    register(settings.deployment.docker_context, settings.deployment.traefik_container)


if __name__ == '__main__':
    main()
