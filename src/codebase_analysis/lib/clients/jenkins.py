"""Authenticated read-only Jenkins artifact transport."""

import base64

from codebase_analysis.lib.clients.http import HttpClient


class JenkinsClient:
    """Share transport and authentication across artifact operations."""

    def __init__(self, client: HttpClient, username: str | None = None,
                 api_token: str | None = None, *, headers: dict[str, str] | None = None) -> None:
        """Configure Basic authentication or copy preconfigured request headers.

        Raises:
            ValueError: Only one Basic authentication field is supplied.
        """
        if bool(username) != bool(api_token):
            raise ValueError("Jenkins username and API token must be supplied together")
        self.client = client
        self.headers = dict(headers or {})
        if username and api_token:
            encoded = base64.b64encode(f"{username}:{api_token}".encode()).decode("ascii")
            self.headers["Authorization"] = f"Basic {encoded}"

    def download(self, url: str) -> bytes:
        """Read an artifact using the configured authentication."""
        return self.client.get(url, self.headers).body
