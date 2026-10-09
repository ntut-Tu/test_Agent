"""Collect remote codebase context for an analysis agent."""

from codebase_analysis.collection import CodebaseAnalysis
from codebase_analysis.models.analysis import AgentResult, AnalysisResult
from codebase_analysis.workflow import CodebaseAnalysisAgent

__all__ = ["AgentResult", "AnalysisResult", "CodebaseAnalysis", "CodebaseAnalysisAgent"]
