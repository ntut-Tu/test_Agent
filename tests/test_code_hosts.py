import unittest

from codebase_analysis.infrastructure.code_hosts.api import GitHubApi, GitLabApi
from codebase_analysis.infrastructure.code_hosts.pr_fetch import (
    GitHubPrFetcher,
    GitLabMrFetcher,
)
from codebase_analysis.infrastructure.code_hosts.test_retriever import (
    GitHubTestRetriever,
    GitLabTestRetriever,
)
from tests.fakes import FakeHttp


class ProviderTests(unittest.TestCase):
    def test_github_fetches_pr_and_remote_test_blob(self):
        root = "https://api.github.com/repos/o/r"
        source_root = "https://api.github.com/repos/contrib/fork"
        routes = {
            root + "/pulls/4": {"title": "Fix", "body": "body", "html_url": "https://github.com/o/r/pull/4", "head": {"sha": "abc", "repo": {"full_name": "contrib/fork"}}, "base": {"sha": "def"}},
            root + "/pulls/4/files?per_page=100&page=1": [{"filename": "src/mod.py", "status": "modified", "patch": "@@ -1 +1 @@\n-a\n+b"}],
            source_root + "/git/commits/abc": {"tree": {"sha": "tree"}},
            source_root + "/git/trees/tree?recursive=1": {"truncated": False, "tree": [{"type": "blob", "path": "tests/test_mod.py", "sha": "blob"}]},
            source_root + "/git/blobs/blob": {"encoding": "base64", "content": "YXNzZXJ0IFRydWU="},
        }
        api = GitHubApi("o/r", "secret", FakeHttp(routes))
        pr = GitHubPrFetcher(api).fetch(4)
        tests, count = GitHubTestRetriever(api).fetch(pr, 5)
        self.assertEqual((pr.title, pr.files[0].path, tests[0].content, count), ("Fix", "src/mod.py", "assert True", 1))

    def test_gitlab_fetches_mr_and_remote_test(self):
        root = "https://gitlab.com/api/v4/projects/group%2Frepo"
        source_root = "https://gitlab.com/api/v4/projects/99"
        routes = {
            root + "/merge_requests/8": {"title": "Fix", "description": "body", "web_url": "https://gitlab.com/group/repo/-/merge_requests/8", "sha": "abc", "diff_refs": {"base_sha": "def"}, "source_project_id": 99},
            root + "/merge_requests/8/diffs?per_page=100&page=1": [{"new_path": "src/mod.py", "old_path": "src/mod.py", "diff": "@@ -1 +1 @@\n-a\n+b"}],
            source_root + "/repository/tree?recursive=true&ref=abc&per_page=100&page=1": [{"type": "blob", "path": "tests/test_mod.py"}],
            source_root + "/repository/files/tests%2Ftest_mod.py/raw?ref=abc": b"assert True",
        }
        api = GitLabApi("group/repo", "secret", FakeHttp(routes))
        pr = GitLabMrFetcher(api).fetch(8)
        tests, count = GitLabTestRetriever(api).fetch(pr, 5)
        self.assertEqual((pr.title, pr.files[0].path, tests[0].content, count), ("Fix", "src/mod.py", "assert True", 1))
