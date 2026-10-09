"""Deploy only test-Agent, using root values and existing Docker networks."""

import os
import subprocess
from pathlib import Path

from codebase_analysis.settings import load_settings

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    settings = load_settings(ROOT / 'values.yaml')
    deployment = settings.deployment
    if len(settings.service.api_token.get_secret_value()) < 32 or not settings.jenkins.base_url:
        raise SystemExit('Configure service.api_token and jenkins.base_url before deploying')
    environment = dict(os.environ, AGENT_UID=str(os.getuid()), AGENT_GID=str(os.getgid()))
    docker = ['docker', '--context', deployment.docker_context]
    compose = docker + ['compose', '-f', 'deploy/compose.yaml']
    for name, network, variable in [
        ('proxy', deployment.traefik_network, 'TRAEFIK_NETWORK'),
        ('jenkins', deployment.jenkins_network, 'JENKINS_NETWORK'),
    ]:
        if network:
            subprocess.run(docker + ['network', 'inspect', network], check=True, stdout=subprocess.DEVNULL)
            environment[variable] = network
            compose += ['-f', f'deploy/compose.{name}.yaml']
    if deployment.published_port:
        environment['AGENT_HOST_PORT'] = str(deployment.published_port)
        compose += ['-f', 'deploy/compose.port.yaml']
    subprocess.run(compose + ['build'], cwd=ROOT, env=environment, check=True)
    subprocess.run(compose + ['up', '-d', '--wait'], cwd=ROOT, env=environment, check=True)
    subprocess.run([os.sys.executable, str(ROOT / "scripts/register_traefik_route.py")], cwd=ROOT, check=True)


if __name__ == '__main__':
    main()
