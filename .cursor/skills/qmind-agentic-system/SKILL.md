---
name: qmind-agentic-system
description: Run the unified agentic pipeline for bias detection, mitigation, and auditing. Use when the user wants to run the full pipeline, orchestrate agents, or execute the Bias Audit Pipeline workflow autonomously.
---

# Bias Audit Pipeline

## Run the Full Pipeline

From project root with venv activated:

```bash
python orchestrator.py
```

Or with venv explicitly:
```bash
.venv/Scripts/python.exe orchestrator.py
```

## What It Does

1. **Detection Agent** — Downloads Credit Card Fraud dataset, injects protected attribute, trains baseline models (LR, Balanced RF), computes fairness metrics.
2. **Judge** — Evaluates detection output (files exist, metrics valid, violations present).
3. **Mitigation Agent** — Applies SMOTE, XGBoost, threshold adjustment; produces comparative matrix.
4. **Judge** — Evaluates mitigation output.
5. **Auditing Agent** — Generates paper sections and compiles draft.
6. **Format Check Agent** — Validates table structure, JSON, and text encoding; applies fixes (SPD Viol/EOD Viol headers, EU threshold footnotes).
7. **Judge** — Evaluates paper (sections, length, tables).
7. **Research Phase** — alphaXiv queries, gap check vs how_biases_are_introduced.pdf, coverage for gaps, reproducibility tests (multiple seeds).

If any core agent fails the judge, the orchestrator retries (up to 3 times) with different random seeds. Research phase runs after the paper is ready; research agents do not block success.

## Outputs

- `outputs/paper_draft.md` — Full paper (Markdown)
- `outputs/paper_sections/*.md` — Individual sections
- `outputs/paper/paper.tex` — LaTeX source
- `outputs/paper/paper.pdf` — Compiled PDF (if pdflatex installed)
- `outputs/figures/*.pdf` — Publication-ready figures (ROC, fairness charts)
- `outputs/baseline_results.json`, `mitigation_results.json`
- `outputs/*.png` — Fairness plots

## Run Individual Agents

```bash
python detection_agent.py [seed]   # default seed=42
python mitigation_agent.py [seed]
python auditing_agent.py
python judge_agent.py [detection|mitigation|auditing]
python structure_review.py        # Structure review (structure + citation research)
python format_check_agent.py       # Validate paper/JSON format; use --fix to auto-correct
```

## Research Phase (integrated)

The research phase runs automatically after the paper is ready:
- **Research Agent** — alphaXiv queries for claims (bias_mitigation, Bias Auditing, Bias Detection PDFs)
- **Gap Check** — vs how_biases_are_introduced.pdf
- **Coverage Agent** — Find papers for gaps (requires `ALPHAXIV_TOKEN`)
- **Reproducibility Agent** — Multiple seeds to verify claims
- **Verification Agent** — Gemini generates Python code, runs it to verify claims (never hardcode). Requires `GOOGLE_API_KEY`.

To run research agents standalone: `python research_orchestrator.py`

## Self-Evolution (Act → Observe → Optimize → Remember)

- **Observe:** Judge + Verification Agent (code-based checks)
- **Optimize:** Revision Agent applies fixes; Optimizer Agent proposes prompt updates from memory
- **Remember:** `memory_agent.py` persists sessions/events to `outputs/memory/`
- **Config:** `configs/prompts/` — trade_off_summary, mitigation_claims (never hardcode)
- **Rule:** `.cursor/rules/self-evolution.mdc`

Run optimizer standalone: `python -m optimizer_agent`

## Gemini-Powered Evaluation (Optional)

Set `GOOGLE_API_KEY` for:
- **Judge Agent:** Semantic evaluation (quality, consistency, claim support) beyond rule-based checks
- **Auditing Hour 6:** Paper structure review, formula verification, citation research via Google Search grounding

Model override: `GEMINI_MODEL=gemini-3.1-pro-preview` (default: gemini-3.1-pro-preview)
