# Product Backlog

## Definitions and recording rules

A **Product Backlog Item (PBI)** describes an improvement to the product. It may be a
feature, defect correction, or technical improvement. A **user story** is one possible
description format; it is not a synonym for every PBI. The Scrum Guide describes the
Product Backlog as an ordered, evolving list and refinement as adding detail. It does
not prescribe the template below. [Source: Scrum Guide](https://scrumguides.org/scrum-guide.html#product-backlog)

This repository uses the following definitions:

- **ID**: permanent reference, such as `PBI-002`. It does not encode priority or a workflow step.
- **Order**: current backlog ordering, maintained separately from the ID.
- **Outcome**: observable value expected from the change.
- **Scope**: behavior included in the item. **Exclusions** identify discussed work outside it.
- **Acceptance criteria (AC)**: item-specific, verifiable conditions; future-tense requirements do not describe delivered functionality.
- **Implementation tasks**: engineering work needed to meet the AC; completing tasks alone does not establish acceptance.
- **Evidence**: named tests, artifacts, or recorded observations, with their verification limits.
- **Status**: `Needs refinement`, `Ready`, `In progress`, or `Done`.
  `Done` requires all AC and the repository completion criteria below to be met.
- **Authorization**: the user's permission to execute a specific scope, separate from status and order.

Repository completion criteria: relevant automated checks pass; behavior and interface
changes are documented; unresolved limitations are recorded; secrets are excluded;
acceptance evidence is linked. Deployment is required only when included in the item's
scope. These are repository conventions, not a claim of a complete organizational Scrum process.

PBI text is maintained in English. Keep implemented behavior, requirements, proposals,
and open decisions explicitly separate. Never silently replace IDs or map an ordinal
such as “item 2” to a different list. Record any split, merge, or scope change.

## Numbering history

The earlier conversation's task list and these PBI IDs are different lists:

| Earlier task | Stable PBI ID | Mapping |
| --- | --- | --- |
| 1: Preserve an analysis baseline | PBI-001 | Implementation task within the architecture item |
| 2: Refactor the project structure | PBI-001 | Main delivery of the architecture item |
| LangGraph workflow and persistence | PBI-002 | Separate follow-up item |

The initial consolidation was not made clear before execution. This table records that
mapping without renumbering existing items or reinterpreting the earlier authorization.

## PBI-001 — Make analysis components identifiable and independently maintainable

- **Order**: 1
- **Status**: Done
- **Authorization**: user instruction to complete the earlier task-list items 1 and 2.
- **Outcome**: maintainers can locate responsibilities by component type and modify an analysis operation without mixing transport, parsing, prompts, and orchestration.
- **Scope**: one Python project; type-based directories; thin tools importing internal libraries; separate collection, workflow, model operations, prompts, schemas, and clients.
- **Exclusions**: LangGraph adoption, prompt improvements, deployment of a new Agent image, and paid model validation.
- **Acceptance criteria**:
  - AC1: Components are organized by type, with no feature/step root directories.
  - AC2: Tools delegate transport and parsing; libraries do not import tools, nodes, or the controller.
  - AC3: The three model operations, prompts, and provider invocation are separate and composed.
  - AC4: Existing tests pass; the synthetic baseline preserves evidence, model messages, JSON schemas, and serialized outputs.
  - AC5: Import boundaries are checked; scripts and architecture documentation reference the implemented paths.
  - AC6: The earlier PR #31/build #7 result and the original baseline are preserved outside Git.
- **Completed tasks**: preserve baseline; separate responsibilities; migrate imports; verify behavior; document architecture and migration.
- **Evidence**: commit `95de553`; 51 local tests; baseline equality; wheel build/import verification; PR #31 live smoke exit 0, with `trace_fetch` warning for producer-declared `complete=False`. [Detailed evidence](structure/structure-refactor.md).
- **Verification limits**: no new live model call or Agent deployment was performed for this item.

## PBI-002 — Execute the analysis with LangGraph and resume persisted progress

- **Order**: 2
- **Status**: Done
- **Authorization**: user explicitly requested implementation after confirming that PBI-002 was not implemented (2026-10-09).
- **Outcome**: an operator can continue a failed or interrupted analysis without repeating model nodes whose outputs were durably saved.
- **Scope**: explicit LangGraph state/nodes/edges; SQLite checkpoints on the existing data volume; queue recovery; distinct resume and fresh-execution operations; compatibility checks.
- **Exclusions**: prompt/output-quality changes, parallel model nodes, automatic retry loops for analysis errors, rate limiting, tracing platforms, multiple workers, live model calls, and deployment into the existing Agent service.
- **Operational definitions**:
  - **Job**: the record deduplicated by the existing immutable build identity.
  - **Generation**: a monotonically increasing identifier for a fresh analysis run within a job. Resuming that run does not change its generation.
  - **Thread**: the LangGraph checkpoint identity for one job generation.
  - **Checkpoint**: durable graph state at a super-step boundary; it is not the commit-message “checkpoint” label.
  - **Resume**: continue the same generation from its saved graph state. If execution never saved an initial checkpoint, start that generation from collection.
  - **Restart**: create a new generation and run from collection without reusing the previous generation's outputs.
- **Acceptance criteria**:
  - AC1: The normal analysis runs through explicit `collect → summarize_pr → analyze_coverage → select_tests → validate` graph nodes and returns the existing `AgentResult` contract. Existing prompt/schema baselines remain unchanged.
  - AC2: Persistent execution uses synchronous checkpoint writes on the service data volume. Closing and reopening the process/storage retains completed node outputs.
  - AC3: After failure in a later node, explicit retry resumes the same generation without repeating durably saved model nodes. A failed/in-flight node may run again. Provider requests are not guaranteed exactly-once.
  - AC4: On worker startup, interrupted `running` jobs are requeued for resume; ordinary `failed` jobs require an explicit retry. Existing queue deduplication and single-worker locking remain effective.
  - AC5: HTTP retry and restart have distinct documented behavior. Status includes the generation and requested execution mode. Active jobs cannot be restarted; repeated build delivery does not create a new generation.
  - AC6: Resume rejects a different build, incompatible workflow contract, or changed analysis configuration before model invocation. When saved source context exists, the current PR head is checked before continuation. A deliberate restart permits the current workflow/configuration.
  - AC7: Existing job databases migrate without losing results. A crash after the graph completes but before the job result is saved can recover the completed graph result.
  - AC8: Checkpoints do not store configured credentials or raw provider exceptions. Evidence/code context remains on the same trusted data volume as job results. HTTP failures remain sanitized.
  - AC9: Automated tests cover failure/resume, fresh restart, process termination/recovery, compatibility rejection, HTTP behavior, and old database migration. The non-LLM remote smoke test and packaging checks pass; any infrastructure limitation is recorded.
- **Implementation tasks**:
  - [x] Define IDs, terms, behavior, compatibility policy, and acceptance criteria.
  - [x] Implement the graph, checkpoint persistence, and compatibility checks.
  - [x] Integrate queue recovery and HTTP execution controls.
  - [x] Verify AC and update actual architecture/API documentation.
- **Compatibility policy**: persist a workflow contract version and a configuration/prompt fingerprint; reject incompatible resume without erasing the old checkpoint. The operator may explicitly restart. No automatic checkpoint migration across incompatible workflow contracts.
- **Dependency**: PBI-001.
- **Evidence**: verified 2026-10-09: 66 local tests pass, including real process termination/recovery with SQLite and HTTP retry/restart; model-message/schema/result baseline unchanged; PR #31 live smoke exit 0 (trace completeness warning only); wheel build and all 69 packaged Python files/imports verified; Ruff and diff checks pass. [AC-to-evidence mapping and verification limits](structure/langgraph-execution.md#acceptance-evidence).
- **Verification limits**: no live model call or deployment of the new Agent image; process recovery was verified using persistent local files, not a restart of the existing Agent container.

## PBI-003 — Bound model request frequency and retries

- **Order**: 3; **Status**: Needs refinement; **Authorization**: not authorized.
- **Outcome**: control waiting time and request volume during analysis.
- **Proposed scope**: a shared in-process rate limiter, timeouts, bounded retries, and available usage metadata configured through values.yaml.
- **Draft AC**: nodes share a limiter; non-retryable failures stop; retry limits are explicit; model/prompt identity, latency, and available token usage are recorded; request limits are distinguished from token/cost budgets.
- **Open decisions**: numeric limits, timeout/retry policy, and ownership relative to graph recovery.
- **Dependencies**: PBI-001; PBI-002 recovery semantics.
- **Evidence**: none; not implemented.

## PBI-004 — Trace analysis execution and model calls

- **Order**: 4; **Status**: Needs refinement; **Authorization**: not authorized.
- **Outcome**: locate failures and inspect the evidence supplied to a model node.
- **Proposed scope**: correlate PR/build/job with node/model invocations and record execution metadata.
- **Draft AC**: correlated traces include duration and failures; credentials are excluded; analysis works when tracing is disabled.
- **Open decisions**: LangSmith versus Langfuse, hosting, and permitted input/output recording.
- **Evidence**: none; no tracing platform has been added.

## PBI-005 — Produce actionable uncovered-code analysis

- **Order**: 5; **Status**: Needs refinement; **Authorization**: not authorized.
- **Outcome**: downstream test generation receives missing behavior, triggering conditions, and expected outcomes.
- **Proposed scope**: use PR summary, diff, and method context; organize output by method/behavior and distinguish evidence from inference.
- **Draft AC**: cited methods/lines exist in the input; suggested conditions/outcomes are explicit; unsupported causes of missing coverage are not presented as facts; deterministic coverage evidence is retained; fixed cases support comparison.
- **Open decisions**: output contract, compatibility, and quality evaluation criteria.
- **Dependency**: PBI-001.
- **Evidence**: none; existing prompts remain unchanged.

## PBI-006 — Evaluate analysis quality across prompt and model versions

- **Order**: 6; **Status**: Needs refinement; **Authorization**: not authorized.
- **Outcome**: evaluate changes against repeatable cases and stated quality criteria.
- **Proposed scope / draft AC**: replayable cases; automated reference/schema checks; human semantic assessment; model/prompt version, latency, and usage records; separation of offline checks and paid validation.
- **Open decisions**: case selection, assessment rubric, and required quality thresholds.
- **Dependency**: agreed PBI-005 evaluation criteria; an external tracing service is optional.
- **Evidence**: PBI-001 provides a behavior baseline, not a semantic-quality benchmark.

## PBI-007 — Deploy and verify a selected Agent release

- **Order**: 7; **Status**: Needs refinement; **Authorization**: no new Agent deployment authorized for PBI-002.
- **Outcome**: Jenkins can submit builds automatically to the selected release through shared Traefik.
- **Proposed scope / draft AC**: container health, authentication, duplicate submissions, recovery, Jenkins integration, and non-LLM smoke validation; deployment sources stay in this repository.
- **Open decisions**: release contents and Jenkins pipeline revision. Live model validation requires applicable authorization.
- **Evidence**: earlier deployment exists; deployment of the forthcoming LangGraph release has not occurred.

## PBI-008 — Explain the relevance or absence of existing test context

- **Order**: 8; **Status**: Needs refinement; **Authorization**: not authorized.
- **Outcome**: distinguish behavior-relevant tests, setup/style references, and absent suitable candidates.
- **Draft AC**: each focal method has context or an absence reason; observed and recommended associations remain distinct; incomplete traces do not prove that a caller is absent.
- **Open decisions**: classification, insufficient-candidate strategy, and output schema.
- **Evidence**: none; not implemented.

## Ideas not selected for implementation

- Skills / Deep Agents middleware: refine only when reusable knowledge, selective context loading, or iterative repair is needed.
- PR Summary: current scope uses title, description, and diff; comment/link retrieval has not been requested.
