import contextlib
import io
import tempfile
import unittest
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

import yaml

from codebase_analysis.lib.errors import RemoteError
from scripts.smoke_test import main
from tests.fakes import FakeHttp


class SmokeTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.values_path = Path(directory.name) / "values.yaml"
        self.values_path.write_text(yaml.safe_dump({
            "llm": {"provider": "", "model": "", "api_key": ""},
            "code_host": {"provider": "gitlab", "repository": "group/repo", "token": "repo-secret"},
            "jenkins": {"artifact_url": "https://jenkins.example/coverage.xml", "metadata_url": "https://jenkins.example/metadata.json"},
        }), encoding="utf-8")
        self.root = "https://gitlab.com/api/v4/projects/group%2Frepo"
        self.pr_url = self.root + "/merge_requests/8"
        self.tree_url = self.root + "/repository/tree?recursive=true&ref=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa&per_page=100&page=1"
        self.coverage_url = "https://jenkins.example/coverage.xml"
        self.routes = {
            self.pr_url: {
                "title": "Fix", "web_url": "https://gitlab.example/mr/8",
                "sha": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "diff_refs": {"base_sha": "def"},
            },
            self.root + "/merge_requests/8/diffs?per_page=100&page=1": [
                {"new_path": "src/main/java/demo/Mod.java", "old_path": "src/main/java/demo/Mod.java", "diff": "@@ -1 +1 @@\n-a\n+b"},
            ],
            self.tree_url: [{"type": "blob", "path": "src/test/java/demo/ModTest.java"}],
            self.root + "/repository/files/src%2Ftest%2Fjava%2Fdemo%2FModTest.java/raw?ref=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa": b"class ModTest { void testX() {} }",
            self.root + "/repository/files/src%2Fmain%2Fjava%2Fdemo%2FMod.java/raw?ref=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa": b"class Mod { int x() { return 1; } }",
            self.coverage_url: (
                b'<coverage><class filename="src/main/java/demo/Mod.java"><lines>'
                b'<line number="1" hits="0"/></lines></class></coverage>'
            ),
        }
        self.routes["https://jenkins.example/metadata.json"] = {
            "schema_version": 1, "revision": "a" * 40,
            "coverage_sha256": sha256(self.routes[self.coverage_url]).hexdigest(),
            "build_id": "job/1", "scope": "Maven verify",
        }
        self.http = FakeHttp(self.routes)

    def run_smoke(self):
        output = io.StringIO()
        with (
            patch("sys.argv", ["smoke_test.py", "8", "--values", str(self.values_path)]),
            patch("codebase_analysis.bootstrap.HttpClient", return_value=self.http),
            patch("codebase_analysis.bootstrap.init_chat_model", side_effect=AssertionError("LLM must not initialize")) as model,
            contextlib.redirect_stdout(output),
        ):
            code = main()
        model.assert_not_called()
        self.assertNotIn("repo-secret", output.getvalue())
        return code, output.getvalue()

    def test_full_collection_uses_remote_adapters_with_blank_llm_settings(self):
        code, output = self.run_smoke()
        self.assertEqual(code, 0)
        for name in ("pr_fetch", "coverage_fetch", "existing_tests", "coverage_match"):
            self.assertIn(f"[PASS] {name}", output)
        self.assertIn("retrieved=1", output)
        self.assertIn("uncovered_lines=1", output)
        self.assertIn(self.coverage_url, [request[1] for request in self.http.requests])

    def test_pr_failure_still_checks_jenkins_and_redacts_remote_error(self):
        original_get = self.http.get
        unauthorized = HTTPError(self.pr_url, 401, "repo-secret", {}, None)
        self.addCleanup(unauthorized.close)

        def get(url, headers=None):
            if url == self.pr_url:
                raise RemoteError("repo-secret") from unauthorized
            return original_get(url, headers)

        self.http.get = get
        code, output = self.run_smoke()
        self.assertEqual(code, 1)
        self.assertIn("[FAIL] pr_fetch: HTTP 401", output)
        self.assertIn("[PASS] coverage_fetch", output)
        self.assertIn("[SKIP] existing_tests", output)
        self.assertIn("[SKIP] coverage_match", output)

    def test_invalid_coverage_still_retrieves_tests_and_returns_failure(self):
        self.routes[self.coverage_url] = b"not XML"
        code, output = self.run_smoke()
        self.assertEqual(code, 1)
        self.assertIn("[FAIL] coverage_fetch", output)
        self.assertIn("[PASS] existing_tests", output)
        self.assertIn("[SKIP] coverage_match", output)

    def test_empty_candidates_and_unmatched_paths_are_visible_warnings(self):
        self.routes[self.tree_url] = []
        self.routes[self.coverage_url] = b"<coverage/>"
        self.routes["https://jenkins.example/metadata.json"]["coverage_sha256"] = sha256(b"<coverage/>").hexdigest()
        code, output = self.run_smoke()
        self.assertEqual(code, 0)
        self.assertIn("[WARN] coverage_fetch: coverage_files=0", output)
        self.assertIn("[WARN] existing_tests: retrieved=0", output)
        self.assertIn("[WARN] coverage_match", output)
        self.assertIn("unmatched_paths=1", output)

    def test_invalid_settings_fail_before_network_access(self):
        self.values_path.write_text("code_host: {}", encoding="utf-8")
        code, output = self.run_smoke()
        self.assertEqual(code, 2)
        self.assertIn("[FAIL] configuration", output)
        self.assertEqual(self.http.requests, [])

    def test_wrong_revision_skips_matching_but_keeps_independent_test_retrieval(self):
        self.routes["https://jenkins.example/metadata.json"]["revision"] = "b" * 40
        code, output = self.run_smoke()
        self.assertEqual(code, 1)
        self.assertIn("[FAIL] coverage_binding: Coverage revision differs", output)
        self.assertIn("[SKIP] coverage_match", output)
        self.assertIn("[PASS] existing_tests", output)
        self.assertNotIn("[PASS] java_context", output)

    def test_missing_provenance_is_failure_not_a_false_matching_success(self):
        values = yaml.safe_load(self.values_path.read_text())
        del values["jenkins"]["metadata_url"]
        self.values_path.write_text(yaml.safe_dump(values))
        code, output = self.run_smoke()
        self.assertEqual(code, 1)
        self.assertIn("[FAIL] coverage_binding: Configure jenkins.metadata_url", output)
        self.assertIn("[SKIP] coverage_match", output)
