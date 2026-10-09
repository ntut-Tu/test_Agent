import json
from dataclasses import dataclass

from codebase_analysis.lib.clients.http import Response
from codebase_analysis.models.coverage import (
    CoverageProvenance,
    CoverageReport,
    FileCoverage,
)
from codebase_analysis.models.pull_request import PullRequest
from codebase_analysis.models.source import ExistingTest


class FakeHttp:
    def __init__(self, routes):
        self.routes = routes
        self.requests = []

    def get(self, url, headers=None):
        self.requests.append(("GET", url, headers))
        value = self.routes[url]
        if isinstance(value, bytes):
            return Response(value, {})
        return Response(json.dumps(value).encode(), {})

@dataclass
class StubPrFetcher:
    pull_request: PullRequest

    def fetch(self, number: int) -> PullRequest:
        assert number == self.pull_request.number
        return self.pull_request


@dataclass
class StubTestRetriever:
    tests: tuple[ExistingTest, ...] = ()
    candidate_count: int = 0

    def fetch(self, pull_request: PullRequest, limit: int, preferred_paths: tuple[str, ...] = ()) -> tuple[tuple[ExistingTest, ...], int]:
        return self.tests[:limit], self.candidate_count


class StubCoverage:
    def fetch(self) -> CoverageReport:
        return CoverageReport((FileCoverage("src/mod.py", frozenset({1})),), "digest", CoverageProvenance("sha", "digest", "job/1", "tests"))
