# Decisions

- 2026-03-10: Captured the runtime contract with two representative fixtures: a detection-pass session that advances into mitigation and an auditing session that stops in `needs_revision` with `revise_claims` metadata.
- 2026-03-10: Kept contract assertions fixture-backed and exact by matching `PipelineEvent.to_queue_dict()` payloads instead of inventing a new event serialization format before runtime implementation exists.
