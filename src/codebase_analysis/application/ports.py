"""Structural interfaces for injected data sources and analysis models."""

from __future__ import annotations

from typing import Protocol

from codebase_analysis.domain.context import SourceMethod, TestContext
from codebase_analysis.domain.models import (
    AnalysisResult,
    CoverageReport,
    ExistingTest,
    LineFinding,
    PullRequest,
)
from codebase_analysis.domain.trace import TraceReport


class PullRequestFetcher(Protocol):
    """Read normalized change metadata from the configured code host."""

    def fetch(self, number: int) -> PullRequest:
        """Fetch a PR/MR and its changed files.

        Args:
            number: Positive repository-scoped PR number or MR IID.

        Returns:
            Metadata, changed files, and source revision for further retrieval.
        """
        ...


class TestRetriever(Protocol):
    """Retrieve test candidates from the PR/MR source revision."""

    def fetch(self, pull_request: PullRequest, limit: int, preferred_paths: tuple[str, ...] = ()) -> tuple[tuple[ExistingTest, ...], int]:
        """Read a bounded selection of existing test files.

        Args:
            pull_request: Change metadata identifying the source revision.
            limit: Positive maximum number of files to retrieve.
            preferred_paths: Observed caller files with priority over heuristics.

        Returns:
            Retrieved files and the total candidate count before the limit.
        """
        ...


class CoverageSource(Protocol):
    """Supply coverage in domain types, independent of artifact format."""

    def fetch(self) -> CoverageReport:
        """Return normalized coverage from the configured report source."""
        ...


class AnalysisModel(Protocol):
    """Perform the three green LLM operations on collected evidence."""

    def summarize_pr(self, context: AnalysisResult) -> str:
        """Summarize a change from its collected metadata and patches.

        Args:
            context: Evidence collected for the PR/MR.

        Returns:
            Generated summary text.
        """
        ...

    def identify_uncovered_lines(self, context: AnalysisResult) -> tuple[LineFinding, ...]:
        """Select relevant uncovered lines and explain their relevance.

        Args:
            context: Evidence containing the allowed coverage candidates.

        Returns:
            Findings referencing supplied path/number pairs; may be empty.
        """
        ...

    def select_existing_tests(self, context: AnalysisResult) -> tuple[TestContext, ...]:
        """Select existing tests relevant to the change.

        Args:
            context: Evidence containing the retrieved test candidates.

        Returns:
            Dynamic associations plus LLM recommendations for focal methods
            without observed callers; may be empty.
        """
        ...


class SourceReader(Protocol):
    """Retrieve source content at the PR/MR source revision."""

    def read(self, pr: PullRequest, path: str) -> str:
        """Return the requested file's UTF-8 source text."""
        ...


class SourceAnalyzer(Protocol):
    """Parse language-specific declarations into domain methods."""

    def parse(self, path: str, content: str) -> tuple[SourceMethod, ...]:
        """Return methods and declaring-file context from source text."""
        ...


class TraceSource(Protocol):
    """Retrieve version-bound per-test method invocation evidence."""

    def fetch(self) -> TraceReport:
        """Return the normalized CI trace artifact."""
        ...
