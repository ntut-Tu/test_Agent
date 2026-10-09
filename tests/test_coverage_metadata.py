import json
import unittest
from dataclasses import replace
from hashlib import sha256
from types import SimpleNamespace

from codebase_analysis.lib.errors import RemoteError
from codebase_analysis.lib.parsers.metadata import parse_metadata
from codebase_analysis.lib.rules.provenance import (
    CoverageBindingError,
    verify_coverage_binding,
)
from codebase_analysis.tools.coverage import JenkinsCoverage
from tests.fakes import FakeHttp
from tests.java_fixtures import REVISION, XML, collector


class CoverageMetadataTests(unittest.TestCase):
    def setUp(self):
        self.payload = {
            'schema_version': 1, 'revision': REVISION,
            'coverage_sha256': sha256(XML).hexdigest(),
            'build_id': 'project/42', 'scope': 'PR head; Maven verify',
        }
        self.http = FakeHttp({'xml': XML, 'metadata': self.payload})
        self.source = JenkinsCoverage('xml', self.http, 'user', 'secret', metadata_url='metadata')

    def test_downloads_metadata_with_same_auth_and_binds_exact_xml(self):
        report = self.source.fetch()
        verify_coverage_binding(report, REVISION)
        self.assertEqual(report.provenance.build_id, 'project/42')
        self.assertEqual(self.http.requests[0][2], self.http.requests[1][2])

    def test_wrong_digest_or_commit_stops_collector_before_reading_source(self):
        for key, value in [('revision', 'b' * 40), ('coverage_sha256', '0' * 64)]:
            with self.subTest(key=key):
                report = self.source.fetch()
                report = replace(report, provenance=replace(report.provenance, **{key: value}))
                configured = collector()
                configured.coverage = SimpleNamespace(fetch=lambda: report)
                configured.source_reader = SimpleNamespace(read=lambda *args: self.fail('Read source before validating coverage'))
                with self.assertRaises(CoverageBindingError):
                    configured.run(1)

    def test_unbound_report_is_rejected(self):
        report = replace(self.source.fetch(), provenance=None)
        with self.assertRaises(CoverageBindingError):
            verify_coverage_binding(report, REVISION)

    def test_invalid_contract_does_not_expose_payload(self):
        for changes in [
            {'schema_version': 2}, {'revision': 'secret'},
            {'coverage_sha256': 'secret'}, {'unknown': 'secret'},
        ]:
            with self.subTest(changes=changes), self.assertRaises(RemoteError) as caught:
                parse_metadata(json.dumps(self.payload | changes).encode())
            self.assertNotIn('secret', str(caught.exception))
