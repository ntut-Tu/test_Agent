from dataclasses import replace
from hashlib import sha256
from types import SimpleNamespace

from codebase_analysis.application.agent import CodebaseAnalysis
from codebase_analysis.domain.models import (
    ChangedFile,
    CoverageProvenance,
    ExistingTest,
    PullRequest,
)
from codebase_analysis.infrastructure.coverage.xml import parse_coverage
from codebase_analysis.infrastructure.source.java import JavaSourceAnalyzer
from tests.fakes import StubPrFetcher, StubTestRetriever

SOURCE_PATH = "src/main/java/demo/ShippingService.java"
TEST_PATH = "src/test/java/demo/ShippingServiceTest.java"
REVISION = "a" * 40
SOURCE = """package demo;
class ShippingService {
    int fee(int amount, boolean express) {
        if (express) {
            return 100;
        }
        return 60;
    }
    int fee(int amount) { return fee(amount, false); }
}
"""
TEST_SOURCE = """package demo;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
@SpringBootTest
class ShippingServiceTest {
    ShippingService service = new ShippingService();
    @Test
    void regularShipping() {
        assertEquals(60, service.fee(10, false));
    }
}
"""
XML = (
    b'<report><package name="demo"><sourcefile name="ShippingService.java">'
    b'<line nr="5" mi="2" ci="0"/><line nr="7" mi="0" ci="2"/>'
    b'<line nr="9" mi="2" ci="0"/></sourcefile></package></report>'
)


def collector(trace=None):
    pr = PullRequest(
        1, "Add express shipping", "", "url", REVISION, "b" * 40,
        (ChangedFile(SOURCE_PATH, "modified", "@@ -4,1 +4,2 @@\n if (express) {\n+return 100;"),),
    )
    report = replace(parse_coverage(XML), artifact_sha256=sha256(XML).hexdigest(),
                     provenance=CoverageProvenance(REVISION, sha256(XML).hexdigest(), "job/1", "Maven verify"))
    return CodebaseAnalysis(
        StubPrFetcher(pr), SimpleNamespace(fetch=lambda: report),
        StubTestRetriever((ExistingTest(TEST_PATH, TEST_SOURCE),), 1),
        source_reader=SimpleNamespace(read=lambda pr, path: {SOURCE_PATH: SOURCE, TEST_PATH: TEST_SOURCE}[path]),
        source_analyzer=JavaSourceAnalyzer(), trace=trace,
    )


def trace_payload():
    return {
        "schema_version": 1, "revision": REVISION,
        "coverage_sha256": sha256(XML).hexdigest(),
        "build_id": "shipping/42", "scope": "Maven test", "complete": True,
        "tests": [{
            "test": {"path": TEST_PATH, "class_name": "demo.ShippingServiceTest", "name": "regularShipping", "line": 8},
            "calls": [{"path": SOURCE_PATH, "class_name": "demo.ShippingService", "name": "fee", "line": 3}],
        }],
    }
