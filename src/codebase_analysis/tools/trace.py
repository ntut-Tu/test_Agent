"""Retrieve and parse Jenkins per-test evidence."""

from codebase_analysis.lib.clients.http import HttpClient
from codebase_analysis.lib.clients.jenkins import JenkinsClient
from codebase_analysis.lib.parsers.trace import parse_trace
from codebase_analysis.models.trace import TraceReport


class JenkinsTrace:
    """Read a trace artifact using the configured Jenkins authentication."""

    def __init__(self, url: str, client: HttpClient, headers: dict[str, str]) -> None:
        """Inject artifact URL, shared HTTP client and authentication headers."""
        self.url = url
        self.client = JenkinsClient(client, headers=headers)
        self.headers = dict(headers)

    def fetch(self) -> TraceReport:
        """Download and validate the trace artifact; failures propagate."""
        return parse_trace(self.client.download(self.url))
