# OpenClaw-Style Agent Runtime Upgrade

## TL;DR
> **Summary**: Convert the current fixed research pipeline into a session-scoped, replayable runtime that preserves existing research-paper outputs while adding run isolation, canonical event/artifact logs, constrained routing, and benchmarkable autonomy.
> **Deliverables**:
> - unified runtime core shared by CLI and GUI
> - session workspace + manifest + replay CLI
> - legacy executor adapters for existing agents
> - constrained routing/tool broker around judge/verification/revision/research
> - pytest-based runtime/replay/benchmark coverage with recorded fixtures
> **Effort**: XL
> **Parallel**: YES - 2 waves
> **Critical Path**: 1 -> 2 -> 3 -> 4 -> 5 -> 6 -> 7 -> 8 -> 9 -> 10

## Context
### Original Request
Create an implementation plan to make the system more agentic and closer to OpenClaw.

### Interview Summary
- Current repo already has judge, verification, revision, memory, typed context, and typed events.
- Main cap is architectural: orchestrators remain fixed subprocess pipelines with shared global `outputs/` state.
- Desired direction is a stronger research-agent runtime, not a general-purpose operator platform.
- Preserve the research-paper product goal and current artifact contracts while upgrading the runtime.

### Metis Review (gaps addressed)
- Use a session-first migration boundary before broader routing.
- Keep existing agents as legacy executors during initial migration.
- Add replay/evals before expanding autonomy breadth.
- Make runtime/session manifests authoritative instead of ad hoc filesystem rehydration.
- Keep routing constrained to the existing judge/verification/revision/research loop.

## Work Objectives
### Core Objective
Replace the duplicated fixed orchestrators with a single session-scoped runtime that can execute the current research workflow, persist canonical session state, replay runs deterministically from recorded fixtures, and support constrained dynamic routing without weakening artifact fidelity.

### Deliverables
- A shared runtime package/core used by `main.py` and `gui/streaming_orchestrator.py`.
- Session directories under `outputs/sessions/<session_id>/` with manifest, event log, artifact index, and replay metadata.
- Legacy executor adapters for `detection`, `mitigation`, `auditing`, `judge`, `verification`, `revision`, and research modules.
- A constrained internal tool broker and routing policy for known runtime actions.
- Replay CLI + fixture mode + benchmark suite for regression and no-network validation.
- Updated runtime tests, integration tests, and minimal operator docs for the new flow.

### Definition of Done (verifiable conditions with commands)
- `pytest tests/runtime -q`
- `pytest tests/integration -q`
- `pytest tests/benchmarks -q`
- `python main.py`
- `python -m runtime.replay --session outputs/sessions/<captured-session-id>/manifest.json`
- `python -m gui.server`

### Must Have
- Session isolation for every run.
- Canonical event + artifact persistence for replay/resume.
- One runtime core shared by CLI and GUI.
- Backward-compatible exported artifacts for the research pipeline.
- No-network fixture coverage for runtime, replay, and failure-path regression.
- Constrained routing only around supported workflow branches.

### Must NOT Have (guardrails, AI slop patterns, scope boundaries)
- No universal planner or open-ended tool marketplace.
- No rewrite of detection/mitigation/auditing logic in the first migration.
- No multi-tenant/distributed execution work.
- No hot-path automatic prompt self-modification.
- No hidden dependence on global `outputs/` after sessioned runtime lands.

## Verification Strategy
> ZERO HUMAN INTERVENTION — all verification is agent-executed.
- Test decision: TDD + `pytest` for runtime, replay, adapter parity, and benchmark coverage
- QA policy: Every task includes executable CLI/API scenarios with fixture-backed happy and failure cases
- Evidence: `.sisyphus/evidence/task-{N}-{slug}.{ext}`

## Execution Strategy
### Parallel Execution Waves
> Target: 5-8 tasks per wave. <3 per wave (except final) = under-splitting.
> Extract shared dependencies as Wave-1 tasks for max parallelism.

Wave 1: runtime contract, unified runtime shell, session ownership, legacy executor adapters, canonical event persistence

Wave 2: replay/rehydration, constrained tool broker, constrained routing, benchmark/eval harness, CLI/GUI cutover + docs

### Dependency Matrix (full, all tasks)
| Task | Depends On | Unlocks |
|------|------------|---------|
| 1 | - | 2, 3, 5, 9 |
| 2 | 1 | 3, 4, 5, 8, 10 |
| 3 | 1, 2 | 4, 6, 10 |
| 4 | 2, 3 | 8, 10 |
| 5 | 1, 2, 3 | 6, 9, 10 |
| 6 | 3, 5 | 9, 10 |
| 7 | 2, 3 | 8, 9 |
| 8 | 4, 5, 7 | 9, 10 |
| 9 | 1, 5, 6, 7, 8 | 10 |
| 10 | 2, 3, 4, 5, 6, 8, 9 | Final verification |

### Agent Dispatch Summary (wave → task count → categories)
| Wave | Task Count | Categories |
|------|------------|------------|
| 1 | 5 | deep, unspecified-high |
| 2 | 5 | deep, unspecified-high, writing |

## TODOs
> Implementation + Test = ONE task. Never separate.
> EVERY task MUST have: Agent Profile + Parallelization + QA Scenarios.

- [ ] 1. Define runtime contract and fixture-backed tests

  **What to do**: Add a `tests/runtime/` suite and recorded fixtures that define the new runtime contract before implementation. Cover session identity, manifest shape, event ordering, artifact index shape, retry metadata, and compatibility expectations for exported paper artifacts.
  **Must NOT do**: Do not implement the runtime first; do not rely on live Gemini, alphaXiv, Kaggle, or GUI interaction for contract tests.

  **Recommended Agent Profile**:
  - Category: `unspecified-high` — Reason: creates the contract that all later runtime work must satisfy.
  - Skills: [] — No specialized skill is required.
  - Omitted: [`playwright`] — Browser automation is unnecessary for contract-first runtime tests.

  **Parallelization**: Can Parallel: NO | Wave 1 | Blocks: 2, 3, 5, 9 | Blocked By: none

  **References** (executor has NO interview context — be exhaustive):
  - Pattern: `utils/schemas.py` — follow existing typed contract style for any new runtime/session dataclasses.
  - Pattern: `utils/events.py` — use current event type naming and queue bridge conventions as the baseline event grammar.
  - Pattern: `utils/context.py` — preserve current artifact-oriented reload behavior as the compatibility baseline.
  - Pattern: `agents/judge_agent.py` — preserve pass/fail + retry hint semantics in recorded fixtures.
  - Pattern: `README.md` — preserve current output contract and pipeline narrative.

  **Acceptance Criteria** (agent-executable only):
  - [ ] `pytest tests/runtime/test_session_contract.py -q` passes.
  - [ ] `pytest tests/runtime/test_event_ordering.py -q` passes.
  - [ ] `pytest tests/runtime/test_artifact_manifest_contract.py -q` passes.
  - [ ] `pytest tests/runtime/test_legacy_output_compat.py -q` passes.

  **QA Scenarios** (MANDATORY — task incomplete without these):
  ```text
  Scenario: Happy path contract fixture validates a passing detection session
    Tool: Bash
    Steps: Run `pytest tests/runtime/test_session_contract.py -q`; capture the generated fixture assertions for `tests/fixtures/runtime/session_detection_pass.json`.
    Expected: Tests pass and assert a session id, ordered lifecycle events, and artifact manifest entries.
    Evidence: .sisyphus/evidence/task-1-runtime-contract.txt

  Scenario: Failure fixture validates retry metadata and no artifact corruption
    Tool: Bash
    Steps: Run `pytest tests/runtime/test_event_ordering.py -q`; inspect the case covering `tests/fixtures/runtime/session_auditing_revision_needed.json`.
    Expected: Tests assert `judge_result -> verification -> revision -> judge_result` ordering and preserve prior attempt records.
    Evidence: .sisyphus/evidence/task-1-runtime-contract-error.txt
  ```

  **Commit**: YES | Message: `test(runtime): add session contract fixtures and failing runtime tests` | Files: `tests/runtime/*`, `tests/fixtures/runtime/*`

- [ ] 2. Add a unified runtime core used by CLI and GUI

  **What to do**: Introduce a shared runtime module that owns run lifecycle, retry orchestration, judge invocation, and post-pass research gating. Refactor `main.py` and GUI orchestration to call this runtime instead of duplicating control flow.
  **Must NOT do**: Do not change agent behavior; do not keep long-term duplicate orchestration logic once the runtime core exists.

  **Recommended Agent Profile**:
  - Category: `deep` — Reason: this is the main architectural seam and highest leverage migration task.
  - Skills: [] — Existing repo patterns are enough.
  - Omitted: [`git-master`] — No git work is needed during implementation.

  **Parallelization**: Can Parallel: NO | Wave 1 | Blocks: 3, 4, 5, 7, 8, 10 | Blocked By: 1

  **References** (executor has NO interview context — be exhaustive):
  - Pattern: `orchestration/orchestrator.py` — baseline CLI flow, retry logic, judge loop, verification/revision branch, research phase trigger.
  - Pattern: `gui/streaming_orchestrator.py` — baseline GUI flow and event streaming expectations.
  - Pattern: `utils/events.py` — preserve queue bridge behavior for GUI consumers.
  - Pattern: `configs/pipeline.yaml` — preserve config-driven agent lists and optimizer/research flags.
  - External: `https://docs.openclaw.ai/concepts/agent-loop` — target shape for session-scoped loop ownership, not a full product clone.

  **Acceptance Criteria** (agent-executable only):
  - [ ] `pytest tests/runtime/test_unified_runtime_core.py -q` passes.
  - [ ] `pytest tests/integration/test_cli_gui_share_runtime.py -q` passes.
  - [ ] `python -m orchestration.orchestrator --help` or equivalent runtime entry command exits 0.

  **QA Scenarios** (MANDATORY — task incomplete without these):
  ```text
  Scenario: CLI path uses the shared runtime core
    Tool: Bash
    Steps: Run `pytest tests/integration/test_cli_gui_share_runtime.py -q -k cli`; then run the CLI entry command under fixture mode.
    Expected: Test proves the CLI delegates to the shared runtime and emits the expected lifecycle events.
    Evidence: .sisyphus/evidence/task-2-unified-runtime-cli.txt

  Scenario: GUI path no longer carries divergent orchestration logic
    Tool: Bash
    Steps: Run `pytest tests/integration/test_cli_gui_share_runtime.py -q -k gui`.
    Expected: Test proves the GUI adapter calls the same runtime core and only adds transport/event wiring.
    Evidence: .sisyphus/evidence/task-2-unified-runtime-gui.txt
  ```

  **Commit**: YES | Message: `feat(runtime): add shared runtime core for cli and gui` | Files: `runtime/*`, `orchestration/orchestrator.py`, `gui/streaming_orchestrator.py`, `main.py`

- [ ] 3. Introduce session workspace ownership and canonical manifests

  **What to do**: Make each run write to `outputs/sessions/<session_id>/` and persist a session manifest, artifact index, config/prompt/resource version snapshot, and attempt metadata. Export backward-compatible top-level artifacts only as explicit runtime outputs, not as the runtime source of truth.
  **Must NOT do**: Do not leave global `outputs/` as the canonical state store; do not invent ambiguous dual sources of truth.

  **Recommended Agent Profile**:
  - Category: `deep` — Reason: session ownership is the critical migration boundary called out by Oracle.
  - Skills: [] — Existing file/schema patterns are sufficient.
  - Omitted: [`playwright`] — Not relevant to workspace/session design.

  **Parallelization**: Can Parallel: NO | Wave 1 | Blocks: 4, 6, 10 | Blocked By: 1, 2

  **References** (executor has NO interview context — be exhaustive):
  - Pattern: `agents/memory_agent.py` — durable run-oriented persistence model to align with session ids.
  - Pattern: `utils/context.py` — existing reload contract that must become compatibility output, not authority.
  - Pattern: `configs/resources/registry.json` — capture resource/prompt versions in the manifest.
  - Pattern: `utils/resource_registry.py` — reuse registry resolution instead of inventing another lookup layer.
  - External: `https://docs.openclaw.ai/concepts/memory` — reference for durable workspace/state ownership principles.

  **Acceptance Criteria** (agent-executable only):
  - [ ] `pytest tests/runtime/test_session_workspace.py -q` passes.
  - [ ] `pytest tests/runtime/test_manifest_version_snapshot.py -q` passes.
  - [ ] `pytest tests/integration/test_legacy_output_export.py -q` passes.

  **QA Scenarios** (MANDATORY — task incomplete without these):
  ```text
  Scenario: Session workspace becomes the source of truth
    Tool: Bash
    Steps: Run `pytest tests/runtime/test_session_workspace.py -q` against fixture session `test-session-001`.
    Expected: Tests assert `outputs/sessions/test-session-001/manifest.json` and `artifacts.json` exist and contain exported artifact pointers.
    Evidence: .sisyphus/evidence/task-3-session-workspace.txt

  Scenario: Legacy export compatibility remains intact
    Tool: Bash
    Steps: Run `pytest tests/integration/test_legacy_output_export.py -q`.
    Expected: Tests assert session-owned artifacts are exported to expected legacy output paths without breaking current schemas.
    Evidence: .sisyphus/evidence/task-3-session-workspace-error.txt
  ```

  **Commit**: YES | Message: `feat(runtime): add session manifests and workspace ownership` | Files: `runtime/session_*`, `utils/context.py`, `configs/resources/registry.json`, `utils/resource_registry.py`

- [ ] 4. Wrap existing agents as legacy executor adapters

  **What to do**: Build adapter objects for subprocess-based agents so the runtime can invoke `detection`, `mitigation`, `auditing`, `judge`, `verification`, `revision`, and research actions through one executor contract while preserving today’s module entrypoints and artifact semantics.
  **Must NOT do**: Do not rewrite the core agent algorithms; do not change JSON schema payloads as part of adapterization.

  **Recommended Agent Profile**:
  - Category: `unspecified-high` — Reason: this is controlled refactoring with compatibility constraints.
  - Skills: [] — Existing subprocess patterns are enough.
  - Omitted: [`frontend-ui-ux`] — No UI work is involved.

  **Parallelization**: Can Parallel: YES | Wave 1 | Blocks: 8, 10 | Blocked By: 2, 3

  **References** (executor has NO interview context — be exhaustive):
  - Pattern: `orchestration/orchestrator.py` — existing module map and retry/judge invocation behavior.
  - Pattern: `gui/streaming_orchestrator.py` — current subprocess streaming behavior for stdout/progress.
  - Pattern: `agents/verification_agent.py` — preserve verification invocation and report output semantics.
  - Pattern: `agents/revision_agent.py` — preserve revision invocation with `JUDGE_FEEDBACK` handoff.
  - Pattern: `agents/reproducibility_agent.py` — preserve multi-seed research execution pattern.

  **Acceptance Criteria** (agent-executable only):
  - [ ] `pytest tests/integration/test_legacy_executor_adapter.py -q` passes.
  - [ ] `pytest tests/runtime/test_executor_result_contract.py -q` passes.
  - [ ] `pytest tests/integration/test_revision_verification_adapter_path.py -q` passes.

  **QA Scenarios** (MANDATORY — task incomplete without these):
  ```text
  Scenario: Legacy detection/mitigation/auditing execute through adapters
    Tool: Bash
    Steps: Run `pytest tests/integration/test_legacy_executor_adapter.py -q`.
    Expected: Tests assert each adapter launches the expected legacy module and returns normalized runtime results.
    Evidence: .sisyphus/evidence/task-4-legacy-adapters.txt

  Scenario: Revision path preserves judge feedback handoff
    Tool: Bash
    Steps: Run `pytest tests/integration/test_revision_verification_adapter_path.py -q`.
    Expected: Tests assert failed auditing triggers verification and revision adapters with the expected feedback payload.
    Evidence: .sisyphus/evidence/task-4-legacy-adapters-error.txt
  ```

  **Commit**: YES | Message: `feat(runtime): add legacy executor adapters` | Files: `runtime/executors/*`, `orchestration/orchestrator.py`, `gui/streaming_orchestrator.py`

- [ ] 5. Persist the canonical event log and attempt records

  **What to do**: Promote event persistence from GUI transport helper to canonical append-only runtime log. Record lifecycle events, attempts, judge results, verification/revision transitions, timestamps, and artifact pointers in session storage for replay and resume.
  **Must NOT do**: Do not rely on in-memory event queues as the only event record; do not create incompatible event naming between runtime and GUI.

  **Recommended Agent Profile**:
  - Category: `unspecified-high` — Reason: event persistence is foundational but bounded.
  - Skills: [] — Existing event abstractions are enough.
  - Omitted: [`playwright`] — Not needed.

  **Parallelization**: Can Parallel: YES | Wave 1 | Blocks: 6, 9, 10 | Blocked By: 1, 2, 3

  **References** (executor has NO interview context — be exhaustive):
  - Pattern: `utils/events.py` — current event taxonomy and queue bridge.
  - Pattern: `gui/server.py` — current WebSocket consumer expectations that must remain compatible.
  - Pattern: `agents/memory_agent.py` — align persisted attempt/result information with long-term run storage.
  - Pattern: `gui/streaming_orchestrator.py` — preserve progress/log emission format while persisting canonical records.

  **Acceptance Criteria** (agent-executable only):
  - [ ] `pytest tests/runtime/test_event_log_persistence.py -q` passes.
  - [ ] `pytest tests/runtime/test_attempt_recording.py -q` passes.
  - [ ] `pytest tests/integration/test_gui_event_bridge_compat.py -q` passes.

  **QA Scenarios** (MANDATORY — task incomplete without these):
  ```text
  Scenario: Event log captures the complete happy-path lifecycle
    Tool: Bash
    Steps: Run `pytest tests/runtime/test_event_log_persistence.py -q`.
    Expected: Tests assert a persisted event log contains ordered `agent_started`, `judge_result`, `outputs_updated`, and `pipeline_finished` records.
    Evidence: .sisyphus/evidence/task-5-event-log.txt

  Scenario: Retry path appends attempts without overwriting prior records
    Tool: Bash
    Steps: Run `pytest tests/runtime/test_attempt_recording.py -q`.
    Expected: Tests assert attempt 1 remains intact after attempt 2 and session metadata includes both outcomes.
    Evidence: .sisyphus/evidence/task-5-event-log-error.txt
  ```

  **Commit**: YES | Message: `feat(runtime): add canonical event logs and attempt persistence` | Files: `runtime/events/*`, `utils/events.py`, `gui/server.py`, `agents/memory_agent.py`

- [ ] 6. Add replay CLI and session rehydration

  **What to do**: Implement a replay command that can rebuild runtime state from a saved session manifest and event log, reproduce recorded control-flow decisions in fixture mode, and resume interrupted runs from the latest durable checkpoint.
  **Must NOT do**: Do not make replay depend on live external services; do not rehydrate arbitrary Python object state without a manifest-backed contract.

  **Recommended Agent Profile**:
  - Category: `deep` — Reason: replay/rehydration is a core architectural capability and trust mechanism.
  - Skills: [] — Existing patterns plus new tests are sufficient.
  - Omitted: [`playwright`] — Replay is runtime-level, not browser-level.

  **Parallelization**: Can Parallel: YES | Wave 2 | Blocks: 9, 10 | Blocked By: 3, 5

  **References** (executor has NO interview context — be exhaustive):
  - Pattern: `utils/context.py` — current limited rehydration behavior that must be superseded by session-backed reload.
  - Pattern: `agents/memory_agent.py` — use persisted run metadata as supporting context, not the sole replay source.
  - Pattern: `orchestration/orchestrator.py` — preserve retry/revision decision semantics during replay.
  - Pattern: `docs/SELF_EVOLUTION_ROADMAP.md` — preserve self-evolution narrative while moving to stronger runtime state ownership.
  - External: `https://docs.openclaw.ai/concepts/agent-loop` — reference for serialized per-session run ownership.

  **Acceptance Criteria** (agent-executable only):
  - [ ] `pytest tests/runtime/test_rehydration.py -q` passes.
  - [ ] `pytest tests/benchmarks/test_replay_harness.py -q` passes.
  - [ ] `python -m runtime.replay --session tests/fixtures/runtime/session_detection_pass.json` exits 0.

  **QA Scenarios** (MANDATORY — task incomplete without these):
  ```text
  Scenario: Replay reproduces a recorded passing session
    Tool: Bash
    Steps: Run `python -m runtime.replay --session tests/fixtures/runtime/session_detection_pass.json`.
    Expected: Replay completes without live network/tool calls and reproduces the recorded lifecycle and artifact assertions.
    Evidence: .sisyphus/evidence/task-6-replay.txt

  Scenario: Rehydration resumes an interrupted auditing session
    Tool: Bash
    Steps: Run `pytest tests/runtime/test_rehydration.py -q -k interrupted_auditing_session`.
    Expected: Test resumes from persisted state and avoids duplicating already-completed attempts.
    Evidence: .sisyphus/evidence/task-6-replay-error.txt
  ```

  **Commit**: YES | Message: `feat(replay): add replay cli and session rehydration` | Files: `runtime/replay.py`, `runtime/session_*`, `tests/runtime/*`, `tests/benchmarks/*`

- [ ] 7. Introduce a constrained internal tool broker and policy layer

  **What to do**: Add a small internal broker for known runtime actions such as legacy agent execution, judge, verification, revision, research, export, and replay. Enforce allowlists, timeouts, file boundaries, and no-network fixture mode in one place.
  **Must NOT do**: Do not build a generic external tool marketplace; do not allow unconstrained file or network access from brokered actions.

  **Recommended Agent Profile**:
  - Category: `deep` — Reason: tool policy becomes critical once routing is less hardcoded.
  - Skills: [] — Existing code and guardrails are sufficient.
  - Omitted: [`security-audit`] — Useful later in implementation, but not required to plan the slice structure.

  **Parallelization**: Can Parallel: YES | Wave 2 | Blocks: 8, 9 | Blocked By: 2, 3

  **References** (executor has NO interview context — be exhaustive):
  - Pattern: `agents/verification_agent.py` — current sandbox/timeout behavior to preserve and centralize.
  - Pattern: `utils/research_client.py` — current external-tool/network boundary that must be policy-controlled.
  - Pattern: `orchestration/sep_layer.py` — keep prompt self-evolution out of the hot runtime path.
  - Pattern: `configs/pipeline.yaml` — use declared runtime components where possible.
  - Pattern: `configs/resources/registry.json` — resolve supported internal actions from registered resources.

  **Acceptance Criteria** (agent-executable only):
  - [ ] `pytest tests/runtime/test_tool_broker_allowlist.py -q` passes.
  - [ ] `pytest tests/runtime/test_tool_broker_timeouts.py -q` passes.
  - [ ] `pytest tests/integration/test_no_network_fixture_mode.py -q` passes.

  **QA Scenarios** (MANDATORY — task incomplete without these):
  ```text
  Scenario: Broker executes only supported runtime actions
    Tool: Bash
    Steps: Run `pytest tests/runtime/test_tool_broker_allowlist.py -q`.
    Expected: Tests pass for supported actions and reject unsupported action ids with a clear runtime error.
    Evidence: .sisyphus/evidence/task-7-tool-broker.txt

  Scenario: Broker enforces timeout and no-network policy
    Tool: Bash
    Steps: Run `pytest tests/runtime/test_tool_broker_timeouts.py -q && pytest tests/integration/test_no_network_fixture_mode.py -q`.
    Expected: Long-running verification/research calls are aborted per policy and fixture mode prevents live network access.
    Evidence: .sisyphus/evidence/task-7-tool-broker-error.txt
  ```

  **Commit**: YES | Message: `feat(runtime): add constrained tool broker and policy guardrails` | Files: `runtime/tools/*`, `runtime/policy/*`, `utils/research_client.py`, `agents/verification_agent.py`

- [ ] 8. Add constrained routing around the existing judge/verification/revision/research loop

  **What to do**: Replace today’s hardcoded branch logic with a declarative routing policy that can choose among supported next steps: retry same executor, invoke verification, invoke revision, re-judge, enter research phase, or terminate. Keep routing bounded to the current research workflow.
  **Must NOT do**: Do not introduce an open-ended planner that invents arbitrary tasks; do not bypass judge/verifier guardrails.

  **Recommended Agent Profile**:
  - Category: `deep` — Reason: routing changes control flow and needs strong guardrails.
  - Skills: [] — Existing orchestration and new broker are enough.
  - Omitted: [`artistry`] — Creative exploration is less valuable than bounded deterministic routing here.

  **Parallelization**: Can Parallel: YES | Wave 2 | Blocks: 9, 10 | Blocked By: 4, 5, 7

  **References** (executor has NO interview context — be exhaustive):
  - Pattern: `orchestration/orchestrator.py` — preserve current retry, verification, revision, and research gates as the initial route set.
  - Pattern: `agents/judge_agent.py` — preserve `passed`, `feedback`, `retry_hint`, and `actionable_feedback` semantics.
  - Pattern: `agents/revision_agent.py` — preserve revision execution contract.
  - Pattern: `agents/verification_agent.py` — preserve contradiction-check path.
  - Pattern: `configs/pipeline.yaml` — route only within declared workflow boundaries.

  **Acceptance Criteria** (agent-executable only):
  - [ ] `pytest tests/runtime/test_routing_policy.py -q` passes.
  - [ ] `pytest tests/integration/test_revision_route.py -q` passes.
  - [ ] `pytest tests/integration/test_research_gate_route.py -q` passes.

  **QA Scenarios** (MANDATORY — task incomplete without these):
  ```text
  Scenario: Judge contradiction routes through verification and revision
    Tool: Bash
    Steps: Run `pytest tests/integration/test_revision_route.py -q`.
    Expected: Test asserts the route sequence is `auditing -> judge fail -> verification -> revision -> judge` with no unsupported detours.
    Evidence: .sisyphus/evidence/task-8-routing.txt

  Scenario: Unsupported or stale route request is rejected cleanly
    Tool: Bash
    Steps: Run `pytest tests/runtime/test_routing_policy.py -q -k unsupported_route`.
    Expected: The runtime returns a deterministic routing error and preserves session integrity.
    Evidence: .sisyphus/evidence/task-8-routing-error.txt
  ```

  **Commit**: YES | Message: `feat(routing): add constrained routing policy for runtime actions` | Files: `runtime/routing/*`, `orchestration/orchestrator.py`, `gui/streaming_orchestrator.py`, `agents/judge_agent.py`

- [ ] 9. Build replay/benchmark/eval coverage for runtime trust

  **What to do**: Add a benchmark and regression harness for the new runtime. Include recorded golden sessions for happy path, retry path, revision path, no-network path, and interrupted resume; measure parity with current exported artifacts and control-flow decisions.
  **Must NOT do**: Do not rely on qualitative “looks more agentic” checks; do not let live LLM variance be the primary regression oracle.

  **Recommended Agent Profile**:
  - Category: `unspecified-high` — Reason: this is broad validation work with many cases, but not a new architecture substrate.
  - Skills: [] — Standard test and fixture work.
  - Omitted: [`playwright`] — Browser automation is optional later; runtime trust should be established headlessly first.

  **Parallelization**: Can Parallel: YES | Wave 2 | Blocks: 10 | Blocked By: 1, 5, 6, 7, 8

  **References** (executor has NO interview context — be exhaustive):
  - Pattern: `agents/reproducibility_agent.py` — use existing reproducibility thinking as a benchmark inspiration, but adapt it to runtime behavior.
  - Pattern: `agents/judge_agent.py` — preserve evaluation semantics in fixture-backed parity checks.
  - Pattern: `README.md` — keep current output expectations visible in benchmark assertions.
  - Pattern: `docs/ROADMAP_AUDIT.md` — preserve already-landed self-evolution capabilities while validating runtime migration.

  **Acceptance Criteria** (agent-executable only):
  - [ ] `pytest tests/benchmarks -q` passes.
  - [ ] `pytest tests/integration/test_runtime_parity.py -q` passes.
  - [ ] `pytest tests/integration/test_no_network_fixture_mode.py -q` passes.

  **QA Scenarios** (MANDATORY — task incomplete without these):
  ```text
  Scenario: Benchmark suite validates golden runtime sessions
    Tool: Bash
    Steps: Run `pytest tests/benchmarks -q`.
    Expected: Benchmarks pass for the recorded happy, retry, revision, and resume fixtures.
    Evidence: .sisyphus/evidence/task-9-benchmarks.txt

  Scenario: Runtime parity fails when exported artifacts drift
    Tool: Bash
    Steps: Run `pytest tests/integration/test_runtime_parity.py -q -k artifact_drift_detection`.
    Expected: The test catches mismatched artifact schemas or control-flow drift and exits non-zero until fixed.
    Evidence: .sisyphus/evidence/task-9-benchmarks-error.txt
  ```

  **Commit**: YES | Message: `feat(evals): add replay benchmarks and runtime parity coverage` | Files: `tests/benchmarks/*`, `tests/integration/*`, `tests/fixtures/runtime/*`

- [ ] 10. Cut over CLI/GUI entrypoints and document the runtime migration

  **What to do**: Finalize entrypoint migration so `main.py`, CLI orchestration, and GUI server all use the sessioned runtime, then update operator-facing docs for session directories, replay, fixture mode, and compatibility guarantees.
  **Must NOT do**: Do not leave dead alternate runtime paths; do not document behavior that is not covered by automated tests.

  **Recommended Agent Profile**:
  - Category: `writing` — Reason: this slice combines entrypoint cleanup with precise operator documentation.
  - Skills: [] — Existing docs/code are sufficient.
  - Omitted: [`frontend-ui-ux`] — The GUI transport is preserved, not redesigned.

  **Parallelization**: Can Parallel: NO | Wave 2 | Blocks: Final verification | Blocked By: 2, 3, 4, 5, 6, 8, 9

  **References** (executor has NO interview context — be exhaustive):
  - Pattern: `main.py` — current CLI entrypoint to replace with runtime-backed bootstrapping.
  - Pattern: `gui/server.py` — preserve start/run/WebSocket API contract while delegating to the unified runtime.
  - Pattern: `SETUP.md` — update operational instructions consistently with current setup conventions.
  - Pattern: `README.md` — update architecture and run instructions only after cutover is complete.
  - Pattern: `gui/streaming_orchestrator.py` — reduce to adapter/transport responsibilities only.

  **Acceptance Criteria** (agent-executable only):
  - [ ] `pytest tests/integration/test_cli_gui_share_runtime.py -q` passes.
  - [ ] `python main.py` exits 0 in fixture mode and writes a session manifest.
  - [ ] `python -m gui.server` starts successfully and `/run` triggers the unified runtime in fixture mode.

  **QA Scenarios** (MANDATORY — task incomplete without these):
  ```text
  Scenario: CLI creates a sessioned runtime run end-to-end
    Tool: Bash
    Steps: Run `python main.py` with fixture-mode environment variables and then `pytest tests/integration/test_cli_gui_share_runtime.py -q -k cli_end_to_end`.
    Expected: The CLI run completes through the shared runtime and writes `outputs/sessions/<session_id>/manifest.json`.
    Evidence: .sisyphus/evidence/task-10-entrypoints-cli.txt

  Scenario: GUI API triggers the same runtime path without orchestration drift
    Tool: Bash
    Steps: Start `python -m gui.server`; send a POST request to `/run` in fixture mode; then run `pytest tests/integration/test_cli_gui_share_runtime.py -q -k gui_end_to_end`.
    Expected: The server responds successfully, enqueues a sessioned run, and the test confirms GUI transport uses the shared runtime path.
    Evidence: .sisyphus/evidence/task-10-entrypoints-gui.txt
  ```

  **Commit**: YES | Message: `feat(runtime): cut over entrypoints and document session runtime` | Files: `main.py`, `gui/server.py`, `gui/streaming_orchestrator.py`, `README.md`, `SETUP.md`

## Final Verification Wave (4 parallel agents, ALL must APPROVE)
- [ ] F1. Plan Compliance Audit — oracle
- [ ] F2. Code Quality Review — unspecified-high
- [ ] F3. Real Manual QA — unspecified-high (+ playwright if UI)
- [ ] F4. Scope Fidelity Check — deep

## Commit Strategy
- Commit by vertical slice, never by layer-only scaffolding.
- Recommended sequence:
  - `test(runtime): add session contract fixtures and failing runtime tests`
  - `feat(runtime): add shared runtime core and session workspace`
  - `feat(runtime): add legacy executor adapters and canonical event log`
  - `feat(replay): add replay CLI and rehydration from session manifests`
  - `feat(routing): add constrained broker and routing policy`
  - `feat(evals): add benchmark harness, fixture mode, and entrypoint cutover`

## Success Criteria
- CLI and GUI both execute through one runtime core.
- Every run writes an isolated session manifest, event log, and artifact index.
- Existing exported research artifacts remain available and schema-compatible.
- Replay reproduces recorded pass/fail control-flow decisions from fixtures.
- No-network runtime tests cover happy path, retry path, revision path, and resume path.
- Routing remains constrained to supported workflow branches and rejects unsupported actions cleanly.
