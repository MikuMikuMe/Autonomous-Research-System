# Learnings

- 2026-03-10: Added the first `tests/runtime/` contract slice around recorded `session.json` fixtures so later runtime work can target exact session identity, retry metadata, and queue payload ordering without hitting live services.
- 2026-03-10: Reused current `utils.schemas` and `PipelineContext.load()` behavior as the compatibility floor; fixture outputs keep the existing `outputs/` paths (`baseline_results.json`, `mitigation_results.json`, `structure_review.json`, `paper_draft.md`, `paper/paper.tex`, `paper/paper.pdf`).
