"""Execute the fixed analysis graph, optionally resuming durable progress."""

from __future__ import annotations

import json
from dataclasses import asdict

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from codebase_analysis.collection import CodebaseAnalysis
from codebase_analysis.interfaces import AnalysisModel
from codebase_analysis.lib.parsers.state import parse_context, parse_result
from codebase_analysis.lib.rules.build import verify_build
from codebase_analysis.models.analysis import AgentResult
from codebase_analysis.models.state import AnalysisState
from codebase_analysis.models.task import BuildRequest
from codebase_analysis.nodes.workflow import WorkflowNodes

# Bump when topology, state shape, or node semantics become incompatible.
WORKFLOW_VERSION = 'codebase-analysis-v1'


class IncompatibleCheckpointError(ValueError):
    """Resume would combine different inputs, workflow contracts or settings."""


class AnalysisNodeError(RuntimeError):
    """A sanitized node failure safe for LangGraph's persisted error writes."""


class CodebaseAnalysisAgent:
    """Compose a sequential LangGraph with optional checkpoint persistence."""

    def __init__(self, collector: CodebaseAnalysis, model: AnalysisModel, *,
                 checkpointer: BaseCheckpointSaver | None = None,
                 configuration_fingerprint: str = '', workflow_version: str = WORKFLOW_VERSION) -> None:
        """Inject evidence/model operations and an externally managed saver.

        The caller owns the checkpointer lifetime. Library calls without a saver
        remain ephemeral. Service calls use one SQLite saver per execution.
        Persistent callers must supply a stable fingerprint for their model,
        prompts and collection settings; bootstrap computes it for service use.
        """
        if checkpointer is not None and not configuration_fingerprint:
            raise ValueError('Persistent execution requires a configuration fingerprint')
        self.collector = collector
        self.model = model
        self.checkpointer = checkpointer
        self.configuration_fingerprint = configuration_fingerprint
        self.workflow_version = workflow_version
        nodes = WorkflowNodes(collector, model)
        builder = StateGraph(AnalysisState)
        previous = START
        for name in ('collect', 'summarize_pr', 'analyze_coverage', 'select_tests', 'validate'):
            operation = getattr(nodes, name)
            builder.add_node(name, self._persistent_node(operation) if checkpointer else operation)
            builder.add_edge(previous, name)
            previous = name
        builder.add_edge(previous, END)
        self.graph = builder.compile(checkpointer=checkpointer)

    @staticmethod
    def _persistent_node(operation):
        def invoke(state: AnalysisState):
            try:
                return operation(state)
            except Exception as exc:
                # LangGraph saves node errors. Never persist provider response text.
                raise AnalysisNodeError(type(exc).__name__) from None
        return invoke

    def run(self, number: int, *, build: BuildRequest | None = None,
            thread_id: str | None = None, resume: bool = False) -> AgentResult:
        """Run a fresh graph or continue the same persisted execution.

        Args:
            number: PR number or MR IID.
            build: Optional immutable CI identity; mandatory in service execution.
            thread_id: Required with a saver; identifies one job generation.
            resume: Continue saved state. If no initial checkpoint exists, start
                that generation from collection. Without a saver, resume is invalid.

        Returns:
            The existing validated AgentResult contract.

        Raises:
            IncompatibleCheckpointError: Stored manifest differs from this run.
            ValueError: Missing persistence identity, invalid input, or stale PR head.
            AnalysisNodeError: A persistent node failed; its message is only an
                exception class name. Ephemeral calls retain original exceptions.
        """
        if number < 1 or (build is not None and number != build.number):
            raise ValueError('Invalid PR/MR number for the submitted build')
        if self.checkpointer is None:
            if resume or thread_id is not None:
                raise ValueError('Resume and thread_id require a checkpointer')
            result = self.graph.invoke({'number': number, 'build': asdict(build) if build else None})
            return parse_result(result['result'])
        if not thread_id:
            raise ValueError('Persistent execution requires thread_id')
        manifest = {
            'workflow_version': self.workflow_version,
            'configuration_fingerprint': self.configuration_fingerprint,
            'number': number, 'build': asdict(build) if build else None,
        }
        contract = json.dumps(manifest, sort_keys=True, ensure_ascii=False)
        config = {'configurable': {'thread_id': thread_id}, 'metadata': {'analysis_contract': contract}}
        saved = self.checkpointer.get_tuple(config)
        if saved is not None:
            if not resume:
                raise ValueError('Thread already exists; resume it or use a new generation')
            if saved.metadata.get('analysis_contract') != contract:
                raise IncompatibleCheckpointError('Checkpoint contract changed; restart with a new generation')
            snapshot = self.graph.get_state(config)
            if 'context' in snapshot.values:
                context = parse_context(snapshot.values['context'])
                verify_build(context, build)
                current = self.collector.pull_requests.fetch(number)
                if current.head_ref != context.pull_request.head_ref:
                    raise ValueError('PR head changed since the saved analysis')
            if not snapshot.next:
                return parse_result(snapshot.values['result'])
            state = None
        else:
            state = {'number': number, 'build': asdict(build) if build else None}
        result = self.graph.invoke(state, config, durability='sync')
        return parse_result(result['result'])
