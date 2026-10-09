import unittest
from unittest.mock import patch
from urllib.parse import quote

from codebase_analysis.bootstrap import build_collector
from codebase_analysis.settings import CollectionSettings
from codebase_analysis.smoke import CollectionSmokeTest
from tests.fakes import FakeHttp
from tests.java_fixtures import (
    REVISION,
    SOURCE,
    SOURCE_PATH,
    TEST_PATH,
    TEST_SOURCE,
    XML,
    trace_payload,
)


class JavaIntegrationTests(unittest.TestCase):
    def test_composed_remote_pipeline_reads_java_xml_and_trace_without_model(self):
        root = "https://gitlab.com/api/v4/projects/group%2Frepo"
        coverage_url = "https://jenkins.example/job/project/42/artifact/jacoco.xml"
        trace_url = "https://jenkins.example/job/project/42/artifact/trace.json"
        routes = {
            root + "/merge_requests/1": {
                "title": "Express shipping", "web_url": "https://gitlab.example/mr/1", "sha": REVISION,
                "diff_refs": {"base_sha": "b" * 40},
            },
            root + "/merge_requests/1/diffs?per_page=100&page=1": [{
                "new_path": SOURCE_PATH, "old_path": SOURCE_PATH,
                "diff": "@@ -4,1 +4,2 @@\n if (express) {\n+return 100;",
            }],
            root + f"/repository/tree?recursive=true&ref={REVISION}&per_page=100&page=1": [
                {"type": "blob", "path": TEST_PATH},
            ],
            root + f"/repository/files/{quote(SOURCE_PATH, safe='')}/raw?ref={REVISION}": SOURCE.encode(),
            root + f"/repository/files/{quote(TEST_PATH, safe='')}/raw?ref={REVISION}": TEST_SOURCE.encode(),
            coverage_url: XML,
            trace_url: trace_payload(),
        }
        settings = CollectionSettings.model_validate({
            "code_host": {"provider": "gitlab", "repository": "group/repo", "token": "repo-secret"},
            "jenkins": {"artifact_url": coverage_url, "trace_url": trace_url, "username": "user", "api_token": "jenkins-secret"},
        })
        http = FakeHttp(routes)
        with patch("codebase_analysis.bootstrap.HttpClient", return_value=http), patch("codebase_analysis.bootstrap.init_chat_model") as model:
            configured = build_collector(settings)
            context = configured.run(1)
            checks = list(CollectionSmokeTest(configured).run(1))
        model.assert_not_called()
        self.assertEqual(len(context.dynamic_test_contexts), 1)
        self.assertEqual(context.dynamic_test_contexts[0].test.file_context, TEST_SOURCE)
        self.assertEqual(context.trace.revision, REVISION)
        jenkins_requests = [request for request in http.requests if request[1] in {coverage_url, trace_url}]
        self.assertEqual(len(jenkins_requests), 4)
        self.assertEqual(jenkins_requests[0][2], jenkins_requests[1][2])
        statuses = {check.name: check.status for check in checks}
        self.assertEqual(statuses["trace_fetch"], "PASS")
        self.assertEqual(statuses["trace_binding"], "PASS")
        self.assertEqual(statuses["java_context"], "PASS")
