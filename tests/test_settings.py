import base64
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from codebase_analysis.bootstrap import build_agent
from codebase_analysis.settings import SettingsError, load_settings


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "values.yaml"
        self.values = {
            "llm": {"provider": "test-provider", "model": "test-model", "api_key": "llm-secret"},
            "code_host": {
                "provider": "gitlab", "repository": "group/project", "token": "repo-secret",
                "api_url": "https://gitlab.example/api/v4",
            },
            "jenkins": {
                "artifact_url": "https://jenkins.example/job/test/1/artifact/coverage.xml",
                "username": "test-user", "api_token": "jenkins-secret",
            },
            "analysis": {"max_test_files": 7},
        }

    def load(self):
        self.path.write_text(yaml.safe_dump(self.values), encoding="utf-8")
        return load_settings(self.path)

    @patch("codebase_analysis.bootstrap.init_chat_model")
    def test_values_reach_model_and_remote_adapters(self, init_model):
        self.values["llm"]["options"] = {"base_url": "https://model.example"}
        for provider in ("gitlab", "github"):
            with self.subTest(provider=provider):
                self.values["code_host"]["provider"] = provider
                settings = self.load()
                agent = build_agent(settings)
                init_model.assert_called_with(
                    "test-model", model_provider="test-provider", api_key="llm-secret",
                    base_url="https://model.example",
                )
                self.assertIs(agent.model.client.chat_model, init_model.return_value)
                self.assertEqual(agent.collector.max_test_files, 7)
                api = agent.collector.pull_requests.api
                self.assertIs(agent.collector.tests.api, api)
                self.assertEqual(api.api_url, "https://gitlab.example/api/v4")
                header = "PRIVATE-TOKEN" if provider == "gitlab" else "Authorization"
                expected = "repo-secret" if provider == "gitlab" else "Bearer repo-secret"
                self.assertEqual(api.headers[header], expected)
                auth = agent.collector.coverage.headers["Authorization"].removeprefix("Basic ")
                self.assertEqual(base64.b64decode(auth).decode(), "test-user:jenkins-secret")
                for secret in ("llm-secret", "repo-secret", "jenkins-secret"):
                    self.assertNotIn(secret, repr(settings))

    def test_invalid_config_errors_hide_secret_values(self):
        self.values["llm"]["api_key"] = {"invalid": "sensitive-value"}
        with self.assertRaises(SettingsError) as caught:
            self.load()
        self.assertIn("llm.api_key", str(caught.exception))
        self.assertNotIn("sensitive-value", str(caught.exception))

    def test_malformed_yaml_errors_hide_source(self):
        self.path.write_text('api_key: ["sensitive-value"', encoding="utf-8")
        with self.assertRaises(SettingsError) as caught:
            load_settings(self.path)
        self.assertNotIn("sensitive-value", str(caught.exception))

    def test_incomplete_credentials_and_unknown_fields_are_rejected(self):
        self.values["jenkins"]["api_token"] = ""
        self.values["analysis"]["max_test_file"] = 5
        with self.assertRaises(SettingsError) as caught:
            self.load()
        self.assertIn("jenkins", str(caught.exception))
        self.assertIn("analysis.max_test_file", str(caught.exception))

    def test_yaml_cannot_construct_python_objects(self):
        self.path.write_text('!!python/object:builtins.object {}', encoding="utf-8")
        with self.assertRaises(SettingsError):
            load_settings(self.path)
