# QMIND Agentic System

A unified agentic pipeline for bias detection, mitigation, and auditing in financial AI systems. The system produces a technically verified research paper on bias in credit-card fraud detection, aligned with EU AI Act fairness thresholds. Agents run autonomously; a **Judge** evaluates quality (rule-based + optional Gemini semantic evaluation); failed agents are retried with feedback until they pass or exhaust retries.

---

## Table of Contents

- [Overview](#overview)
- [6-Hour Research Game Plan](#6-hour-research-game-plan)
- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [Components](#components)
- [Data Flow & Contracts](#data-flow--contracts)
- [Judge Quality Criteria](#judge-quality-criteria)
- [Gemini-Powered Evaluation](#gemini-powered-evaluation)
- [Configuration](#configuration)
- [Setup & Run](#setup--run)
- [Outputs](#outputs)
- [Extension Points](#extension-points)
- [Troubleshooting](#troubleshooting)

---

## Overview

The pipeline implements a **6-hour research sprint** (see [howto.md](howto.md)): from dataset loading to a submission-ready paper with LaTeX and PDF. Each agent corresponds to specific hours and deliverables:

| Stage | Agent | Hours | Output |
|-------|-------|-------|--------|
| 1 | **Detection** | 1, 2 | Baseline models (LR, Balanced RF), fairness metrics, ROC curves, data splits |
| 2 | **Mitigation** | 3 | SMOTE + XGBoost, threshold adjustment, comparative matrix, asymmetric cost analysis |
| 3 | **Auditing** | 1–6 | Paper sections, Markdown draft, LaTeX paper, Hour 6 review |

After each agent runs, the **Judge** evaluates its output. If the Judge fails an agent, the orchestrator retries (up to 3 times) with different random seeds. The pipeline stops on persistent failure.

---

## 6-Hour Research Game Plan

The pipeline is structured around the research sprint in [howto.md](howto.md):

| Hour | Goal | Agent(s) | Deliverable |
|------|------|----------|-------------|
| **1** | Scope, setup, delegation | Detection, Mitigation, Auditing | Dataset loaded, SMOTE/threshold code ready, Intro & Background |
| **2** | Baseline technical proof | Detection | LR + Balanced RF, DPD/EOD/DI metrics, baseline table |
| **3** | Implementing mitigation | Mitigation | SMOTE + XGBoost, threshold adjustment, comparative matrix, asymmetric cost |
| **4** | Drafting core sections | Auditing, Detection, Mitigation | Bias Auditing, Methodology, Results, figures exported, LaTeX paper |
| **5** | Synthesis and discussion | Auditing | Discussion section (model selection, trade-off, post-processing limits) |
| **6** | Review, format, citations | Auditing | Structure review, formula check, citation research (Gemini + Google Search) |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                         ORCHESTRATOR (orchestrator.py)                          │
│  • Runs: Detection → Mitigation → Auditing → Research (alphaXiv, gap, repro)   │
│  • Invokes Judge after each agent                                              │
│  • Retries failed agents with seed=42, 43, 44 (up to 3 attempts)               │
└─────────────────────────────────────────────────────────────────────────────────┘
         │                         │                         │
         ▼                         ▼                         ▼
┌──────────────────┐    ┌──────────────────┐    ┌──────────────────────────┐
│ Detection Agent  │    │ Mitigation Agent  │    │ Auditing Agent            │
│ (Hours 1–2)      │    │ (Hours 3–4)      │    │ (Hours 1–6)               │
│                  │    │                  │    │                            │
│ • Kaggle dataset │    │ • Load baseline  │    │ • Intro, Background       │
│ • Synthetic attr │    │ • SMOTE          │    │ • Methodology, Results   │
│ • LR, BRF        │    │ • XGBoost        │    │ • Audit Framework         │
│ • Fairness metrics│   │ • Threshold adj  │    │ • Discussion (Hour 5)     │
│ • ROC, bar charts│    │ • Asymmetric cost│    │ • LaTeX + PDF (Hour 4)    │
│ • npz, json      │    │ • Figures        │    │ • Hour 6 review           │
└────────┬─────────┘    └────────┬─────────┘    └────────────┬─────────────────┘
         │                      │                          │
         └──────────────────────┼──────────────────────────┘
                                ▼
                    ┌───────────────────────────┐
                    │   JUDGE AGENT             │
                    │                           │
                    │ • Rule-based: files,      │
                    │   schema, sections, tables │
                    │ • Gemini (optional):      │
                    │   quality, consistency,   │
                    │   claim support           │
                    └───────────────────────────┘
```

**Execution model:** Agents run as subprocesses (`python -m detection_agent 42`). The orchestrator does not modify agent code; it controls invocation order, seed, and retry count.

---

## Project Structure

```
QMIND-Agent/
├── orchestrator.py          # Main entry: runs pipeline + Judge loop (CLI)
├── run_gui.py               # GUI entry: web dashboard
├── judge_agent.py            # Quality evaluation (rule-based + Gemini)
├── detection_agent.py        # Bias detection (Hours 1–2)
├── mitigation_agent.py       # Bias mitigation (Hours 3–4)
├── auditing_agent.py         # Paper generation (Hours 1–6)
├── llm_client.py             # Gemini API client (Judge, Hour 6)
├── latex_generator.py        # LaTeX paper with figures, formulas, bibliography
├── hour6_review.py           # Hour 6: structure review, citation research
├── gui/                      # Web dashboard
│   ├── server.py             # FastAPI + WebSocket
│   ├── streaming_orchestrator.py
│   └── static/               # index.html, app.js
├── requirements.txt
├── README.md                 # This document
├── SETUP.md                  # Setup (venv, Kaggle, LaTeX, Gemini)
├── howto.md                  # 6-hour research sprint guide
├── kaggle.json.example       # Kaggle credential template
├── env.example               # Gemini API key template
├── docs/
│   ├── ALPHAXIV_SETUP.md     # alphaXiv MCP integration
│   └── RESEARCH_CHECKLIST.md # Coverage checklist from research outlines
├── .cursor/
│   ├── mcp.json              # alphaXiv MCP config (add token)
│   └── skills/
│       └── qmind-agentic-system/
│           └── SKILL.md      # Cursor skill for pipeline
├── .venv/                    # Python virtual environment
└── outputs/                  # Generated artifacts (created at runtime)
    ├── data_splits.npz
    ├── baseline_results.json
    ├── mitigation_results.json
    ├── mitigation_comparison.png
    ├── figures/
    │   ├── fig_baseline_fairness.{png,pdf}
    │   ├── fig_baseline_roc.{png,pdf}
    │   └── fig_mitigation_comparison.{png,pdf}
    ├── paper_draft.md
    ├── paper_sections/
    │   ├── 01_introduction.md
    │   ├── 02_background.md
    │   ├── 03_methodology_and_results.md
    │   ├── 04_audit_framework.md
    │   ├── 05_discussion.md
    │   └── 06_references.md
    ├── paper/
    │   ├── paper.tex
    │   ├── paper.pdf          # If pdflatex installed
    │   └── references.bib
    └── hour6_review.json
```

---

## Components

### Orchestrator (`orchestrator.py`)

- **Role:** Central controller. Runs agents in order, calls Judge, handles retries.
- **Constants:** `MAX_RETRIES = 3`, `AGENTS = ["detection", "mitigation", "auditing"]`
- **Key functions:**
  - `run_agent(agent_name, seed)` — subprocess `python -m <module> <seed>`
  - `run_judge(agent_name)` — imports and calls `judge_agent.evaluate(agent_name)`
- **Exit:** `sys.exit(1)` if any agent fails after all retries.

### Judge Agent (`judge_agent.py`)

- **Role:** Evaluate agent outputs. Return `{passed, feedback[], retry_hint}`.
- **Modes:**
  - **Rule-based (always):** File existence, schema, section names, table presence.
  - **Gemini (when `GOOGLE_API_KEY` set):** Semantic evaluation of quality, consistency, claim support.
- **API:** `evaluate(agent_name)`, `evaluate_all()`
- **CLI:** `python judge_agent.py [detection|mitigation|auditing]`

### Detection Agent (`detection_agent.py`)

- **Role:** Download Credit Card Fraud dataset, inject synthetic protected attribute, train baseline models, compute fairness metrics.
- **Hours:** 1 (setup), 2 (baseline proof), 4 (export figures)
- **Input:** Kaggle dataset `mlg-ulb/creditcardfraud` (via kagglehub)
- **Output:** `data_splits.npz`, `baseline_results.json`, `figures/fig_baseline_*.{png,pdf}`
- **CLI:** `python detection_agent.py [seed]`

### Mitigation Agent (`mitigation_agent.py`)

- **Role:** Load Detection outputs, apply SMOTE, train XGBoost, apply threshold adjustment, produce comparative matrix and asymmetric cost analysis.
- **Hours:** 1 (setup), 2 (load baseline), 3 (mitigation), 4 (export figures)
- **Input:** `data_splits.npz`, `baseline_results.json`
- **Output:** `mitigation_results.json`, `mitigation_comparison.png`, `figures/fig_mitigation_comparison.{png,pdf}`
- **CLI:** `python mitigation_agent.py [seed]`

### Auditing Agent (`auditing_agent.py`)

- **Role:** Generate paper sections from templates + Detection/Mitigation JSON, compile draft, generate LaTeX, run Hour 6 review.
- **Hours:** 1 (Intro, Background), 2 (Methodology), 4 (LaTeX), 5 (Discussion), 6 (Review)
- **Input:** `baseline_results.json`, `mitigation_results.json`
- **Output:** `paper_sections/*.md`, `paper_draft.md`, `paper/paper.tex`, `paper/paper.pdf`, `hour6_review.json`
- **CLI:** `python auditing_agent.py`

### LLM Client (`llm_client.py`)

- **Role:** Gemini API wrapper for Judge and Auditing agents.
- **Config:** `GOOGLE_API_KEY` or `GEMINI_API_KEY`, `GEMINI_MODEL` (default: `gemini-3.1-pro-preview`)
- **Features:** `generate()`, `generate_with_grounding()` (Google Search), `generate_json()`
- **Optional:** Loads `.env` via `python-dotenv` if installed.

### LaTeX Generator (`latex_generator.py`)

- **Role:** Generate publication-ready LaTeX paper in **IEEE/CUCAI 2026 format** (IEEEtran, two-column, IEEE-style citations) with figures, formulas (SPD, DI, EOD, Accuracy, F1), tables, bibliography.
- **Output:** `outputs/paper/paper.tex`, `outputs/paper/paper.pdf` (if pdflatex installed)

### Hour 6 Review (`hour6_review.py`)

- **Role:** Review paper structure, verify formulas, run citation research via Gemini + Google Search grounding.
- **Output:** `outputs/hour6_review.json`
- **CLI:** `python hour6_review.py`

---

## Data Flow & Contracts

### Detection → Mitigation

| File | Format | Contents |
|------|--------|----------|
| `data_splits.npz` | NumPy archive | `X_train`, `X_test`, `y_train`, `y_test`, `A_train`, `A_test` |
| `baseline_results.json` | JSON | `{ "baseline_metrics": [ {...}, {...} ] }` |

**Metric schema (per model):**
```json
{
  "model": "Logistic Regression",
  "accuracy": 0.9786,
  "f1_score": 0.1247,
  "auc": 0.9681,
  "false_positive_rate": 0.021185,
  "demographic_parity_diff": 0.0285,
  "equalized_odds_diff": 0.7275,
  "disparate_impact_ratio": 0.2269,
  "positive_rate_group_0": 0.008374,
  "positive_rate_group_1": 0.036908,
  "eu_ai_act_spd_violation": false,
  "eu_ai_act_eod_violation": true
}
```

### Mitigation → Auditing

| File | Format | Contents |
|------|--------|----------|
| `mitigation_results.json` | JSON | `{ "baseline_metrics": [...], "mitigation_metrics": [...], "asymmetric_cost_analysis": {...} }` |

**Asymmetric cost schema:**
```json
{
  "best_baseline_model": "Balanced Random Forest",
  "best_mitigated_model": "Threshold-Adj (XGBoost+SMOTE)",
  "accuracy_delta": -0.0225,
  "fpr_delta": 0.022639,
  "dpd_improvement": -0.0131,
  "eod_improvement": -0.3928,
  "trade_off_summary": "..."
}
```

---

## Judge Quality Criteria

Defined in `judge_agent.py`:

| Agent | Criterion | Constant |
|-------|-----------|----------|
| **Detection** | `data_splits.npz` exists | — |
| | `baseline_results.json` exists, valid JSON | — |
| | ≥ 2 baseline models | `MIN_DETECTION_MODELS = 2` |
| | Each model has required keys | `REQUIRED_KEYS_DETECTION` |
| | ≥ 1 model with SPD or EOD violation | — |
| **Mitigation** | `mitigation_results.json` exists | — |
| | `baseline_metrics` ≥ 2, `mitigation_metrics` ≥ 2 | `MIN_MITIGATION_STRATEGIES = 2` |
| | `mitigation_comparison.png` exists | — |
| **Auditing** | `paper_draft.md` exists | — |
| | Draft length ≥ 2000 chars | `MIN_PAPER_LENGTH = 2000` |
| | Sections: Introduction, Background, Use Case, Audit Framework, Discussion, References | `REQUIRED_PAPER_SECTIONS` |
| | Contains `\| Model` or `Table` (results tables) | — |

**Retry hints:** `detection`, `mitigation`, `auditing`, or `detection:try_different_seed` (when no violations found).

---

## Gemini-Powered Evaluation

When `GOOGLE_API_KEY` (or `GEMINI_API_KEY`) is set:

### Judge Agent

- **Detection:** Evaluates metric consistency, whether results support "baseline violates EU AI Act."
- **Mitigation:** Evaluates fairness improvement, asymmetric cost demonstration, claim support.
- **Auditing:** Evaluates claim–data alignment, section coherence, formula presence.

Returns PASS/FAIL with reasoning; can fail on semantic issues even if rule-based checks pass.

### Auditing Hour 6

- **Structure review:** Verifies required sections (Background, Use Case, Detection, Mitigation, Audit, Discussion) and formulas (Demographic Parity, Disparate Impact, Equalized Odds, Accuracy, F1).
- **Citation research:** Uses Gemini with Google Search grounding to find recent (2023–2025) papers supporting the claims.

**Setup:** See [SETUP.md](SETUP.md). Model override: `GEMINI_MODEL=gemini-2.0-flash` (default: `gemini-1.5-pro`).

---

## alphaXiv MCP (Optional)

When configured, Cursor's AI can search papers via [alphaXiv](https://alphaxiv.org) to support and prove the research. Use it to:

- Search for papers by title (`search_for_paper_by_title`)
- Discover trending papers by topic (`find_papers_feed`: cs.AI, cs.LG, bias mitigation)
- Query PDFs for methodology/results (`answer_pdf_queries`)
- Synthesize answers from multiple papers (`answer_research_query`)

**Setup:** See [docs/ALPHAXIV_SETUP.md](docs/ALPHAXIV_SETUP.md). Add your token to `.cursor/mcp.json` and restart Cursor. For the **research pipeline** (Python agents), also add `ALPHAXIV_TOKEN` to `.env`.

**Research phase:** The unified pipeline runs research automatically after the paper is ready. Set `ALPHAXIV_TOKEN` in `.env` for alphaXiv queries.

**Research checklist:** [docs/RESEARCH_CHECKLIST.md](docs/RESEARCH_CHECKLIST.md) maps all points from the research outlines (how_biases_are_introduced.pdf, bias_mitigation.pdf, Bias Auditing Framework) for full coverage.

---

## Configuration

| Location | Variable | Default | Purpose |
|----------|----------|---------|---------|
| `orchestrator.py` | `MAX_RETRIES` | 3 | Max attempts per agent |
| `orchestrator.py` | `AGENTS` | `["detection","mitigation","auditing"]` | Core pipeline order |
| `orchestrator.py` | `RESEARCH_AGENTS` | research, gap_check, coverage, reproducibility | Runs after paper ready |
| `judge_agent.py` | `MIN_DETECTION_MODELS` | 2 | Required baseline count |
| `judge_agent.py` | `MIN_MITIGATION_STRATEGIES` | 2 | Required mitigation count |
| `judge_agent.py` | `MIN_PAPER_LENGTH` | 2000 | Min draft chars |
| `judge_agent.py` | `REQUIRED_PAPER_SECTIONS` | [...] | Section names |
| `llm_client.py` | `GEMINI_MODEL` | `gemini-3.1-pro-preview` | Gemini model |
| `llm_client.py` | `GOOGLE_API_KEY` | env | API key |
| All agents | `OUTPUT_DIR` | `outputs/` | Output directory |

---

## Setup & Run

### Quick Start

```bash
# Create and activate venv
python -m venv .venv
.venv\Scripts\Activate.ps1   # Windows PowerShell

# Install dependencies
pip install -r requirements.txt

# Run full pipeline
python orchestrator.py
```

### Running with GUI

A web dashboard streams live logs, metrics, figures, paper sections, and Judge feedback. On success, the research paper (PDF or Markdown) opens automatically.

```bash
python run_gui.py
```

Open http://127.0.0.1:8000 in your browser, then click **Run Pipeline**. The CLI (`python orchestrator.py`) remains available for headless runs.

### Individual Agents

```bash
python detection_agent.py [seed]   # default seed=42
python mitigation_agent.py [seed]
python auditing_agent.py
python judge_agent.py [detection|mitigation|auditing]
python judge_agent.py               # evaluate all
python hour6_review.py              # Hour 6 review standalone
```

### Optional Setup

- **Kaggle:** For dataset download. See [SETUP.md](SETUP.md).
- **LaTeX:** For PDF compilation. See [SETUP.md](SETUP.md).
- **Gemini API:** For semantic evaluation and citation research. See [SETUP.md](SETUP.md).

---

## Outputs

| Path | Description |
|------|-------------|
| `outputs/paper_draft.md` | Full paper (Markdown) |
| `outputs/paper_sections/*.md` | Individual sections |
| `outputs/paper/paper.tex` | LaTeX source |
| `outputs/paper/paper.pdf` | Compiled PDF (if pdflatex installed) |
| `outputs/figures/*.pdf` | Publication-ready figures |
| `outputs/baseline_results.json` | Detection metrics |
| `outputs/mitigation_results.json` | Mitigation metrics + asymmetric cost |
| `outputs/hour6_review.json` | Hour 6 structure + citation research |

---

## Retry Logic

1. Orchestrator runs agent with `seed=42` (first attempt).
2. Judge evaluates. If **pass** → continue to next agent.
3. If **fail:** retry with `seed=42+attempt` (43, 44). Auditing has no seed; retry re-runs with latest JSON.
4. After 3 failures, pipeline stops and exits with code 1.

**When retries help:** Different seed → different protected attribute / train split → may produce fairness violations.

---

## Extension Points

### Adding a New Agent

1. Create `new_agent.py` with `main(seed=42)` (or `main()` if deterministic).
2. Add to `orchestrator.py`: `module_map`, `AGENTS`.
3. Add `evaluate_new_agent()` in `judge_agent.py` and register in `evaluate()`.
4. Define output contract and Judge criteria.

### Customizing Judge Criteria

Edit `judge_agent.py`: `REQUIRED_KEYS_*`, `MIN_*`, `REQUIRED_PAPER_SECTIONS`, or add checks in `evaluate_*()`.

### Config File

Add `config.yaml` and load in orchestrator and judge; pass to agents via env or args.

---

## Troubleshooting

| Issue | Cause | Fix |
|-------|-------|-----|
| `FileNotFoundError: data_splits.npz` | Mitigation run before Detection | Run `orchestrator.py` or `detection_agent.py` first |
| Judge: "No fairness violations" | Seed produced balanced groups | Retry with different seed (orchestrator does this) |
| Judge: "Missing section: X" | Section name mismatch | Update `REQUIRED_PAPER_SECTIONS` in `judge_agent.py` |
| Kaggle auth error | No/missing credentials | Add `kaggle.json` to `~/.kaggle/` (see SETUP.md) |
| Pipeline stops at Detection | Detection fails 3 times | Run `python judge_agent.py detection` for feedback |
| Gemini not used | No API key | Set `GOOGLE_API_KEY` (see SETUP.md) |
| PDF not generated | pdflatex not installed | Install MiKTeX/TeX Live or compile manually |

---

## Quick Reference

```bash
# Full pipeline
python orchestrator.py

# Individual agents
python detection_agent.py [seed]
python mitigation_agent.py [seed]
python auditing_agent.py

# Judge only
python judge_agent.py [detection|mitigation|auditing]
python judge_agent.py   # evaluate all

# Hour 6 review
python hour6_review.py
```

See [SETUP.md](SETUP.md) for venv, Kaggle, LaTeX, and Gemini setup. See [howto.md](howto.md) for the 6-hour research game plan.
