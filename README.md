# Autonomous Research System

A general-purpose, self-evolving multi-agent platform that autonomously researches, cross-validates claims, detects flaws, learns from past trials, and evolves toward quantifiable results. Two modes:

1. **Goal-Oriented** (default) — Iteratively research toward a quantifiable goal. The system converges when claims are verified above a configurable threshold.
2. **Report / Deep-Dive** — Produce a comprehensive research report on a topic with thorough literature review.

### Key v2.0 Features

- **Multi-LLM support** — `BaseLLMClient` ABC with `GeminiClient`, `OpenAIClient`, `AnthropicClient`; provider priority list in `pipeline.yaml`
- **Hardened code execution sandbox** — Import blocklist, static analysis, runtime import hooks, env-var stripping, optional Docker container isolation
- **Distributed tracing** — OpenTelemetry (OTLP/Jaeger) + LangSmith; context managers and decorators
- **Progressive config loading** — Thread-safe lazy-loaded prompt templates and rules
- **In-process state objects** — `ResearchContext` with typed `ClaimState`, `Technique`, `Flaw` dataclasses
- **Web search integration** — Tavily + arXiv + Semantic Scholar
- **MCP integration** — Model Context Protocol for domain tools
- **Cross-session memory** — Persistent user profiles across pipeline runs
- **Modern React GUI** — Vite + Tailwind + React 19, WebSocket streaming
- **Docker Compose deployment** — FastAPI server + optional pdflatex sidecar
- **Telegram bot** — Thin wrapper over WebSocket/REST API

---

## Table of Contents

- [Overview](#overview)
- [Research Workflow](#research-workflow)
- [Continuous Research Loop](#continuous-research-loop)
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

The pipeline runs from dataset loading to a submission-ready paper with LaTeX and PDF. Each agent corresponds to specific stages and deliverables:

| Stage | Agent | Output |
|-------|-------|--------|
| 1 | **Detection** | Baseline models (LR, Balanced RF), fairness metrics, ROC curves, data splits |
| 2 | **Mitigation** | SMOTE + XGBoost, threshold adjustment, comparative matrix, asymmetric cost analysis |
| 3 | **Auditing** | Paper sections, Markdown draft, LaTeX paper, structure review |

After each agent runs, the **Judge** evaluates its output. If the Judge fails an agent, the orchestrator retries (up to 3 times) with different random seeds. The pipeline stops on persistent failure.

---

## Research Workflow

The pipeline automates the end-to-end workflow for producing a technically verified research paper on bias in financial AI.

### Narrative

The paper argues that traditional classifiers (Logistic Regression, Random Forest) inherit representational bias from training data, and that complying with regulatory frameworks like the **EU AI Act** requires specific mitigation strategies. The pipeline proves this technically using real experimental data.

### Detection (Baseline Proof)

The Detection Agent trains baseline models on the [MLG-ULB Credit Card Fraud Detection](https://www.kaggle.com/datasets/mlg-ulb/creditcardfraud) dataset with a synthetic protected attribute and computes fairness metrics:

- **Disparate Impact (DI):** Proves the proportion of positive outcomes between demographics is skewed.
- **Equalized Odds (EOD):** Proves that false positive / false negative rates disproportionately affect one demographic.
- **Deliverable:** A baseline table showing high accuracy but severe violations of EU AI Act fairness thresholds (|SPD| > 0.1 or |EOD| > 0.05).

### Mitigation (The Fix)

The Mitigation Agent applies strategies referenced in the literature:

1. **Pre-processing (SMOTE):** Balances the dataset to fix representational bias. XGBoost responds better to SMOTE than Random Forest.
2. **Post-processing (Threshold Adjustment):** Dynamically adjusts decision boundaries for the disadvantaged group.
- **Deliverable:** A comparative matrix (Accuracy vs. Fairness) that technically proves the "asymmetric cost" --- mitigating bias may slightly lower accuracy or increase false positives, establishing the accuracy/fairness trade-off.

### Auditing (Paper Generation)

The Auditing Agent generates the full paper structure:

1. **Background & Taxonomy** --- Sources of bias, fairness metrics, EU AI Act
2. **Use Case & Data** --- Dataset, synthetic protected attribute, model configurations
3. **Detection Results** --- Baseline fairness metrics with violation flags
4. **Mitigation Experiments** --- Comparative matrix, asymmetric cost analysis
5. **Bias Audit Framework** --- Lifecycle-based oversight (pre-deployment, monitoring, post-deployment, governance)
6. **Discussion** --- Model selection matters, accuracy/fairness trade-off, post-processing limits

The paper is compiled to IEEE/CUCAI 2026 format LaTeX and PDF.

### Research & Verification

After the paper is ready, the research phase automatically:

- Queries alphaXiv / arXiv / Semantic Scholar for papers supporting claims
- Checks coverage against reference PDFs (gap analysis)
- Runs detection/mitigation with multiple seeds to verify reproducibility
- Generates verification code to validate numerical claims

### Quick Reference (Fairlearn)

```python
from fairlearn.metrics import demographic_parity_difference, equalized_odds_difference
from imblearn.over_sampling import SMOTE
from xgboost import XGBClassifier

# Baseline bias detection
baseline_model = XGBClassifier().fit(X_train, y_train)
y_pred = baseline_model.predict(X_test)
dp_diff = demographic_parity_difference(y_test, y_pred, sensitive_features=A_test)
eo_diff = equalized_odds_difference(y_test, y_pred, sensitive_features=A_test)
# Compare against EU AI Act thresholds: |SPD| <= 0.1, |EOD| <= 0.05

# Mitigation via pre-processing (SMOTE)
smote = SMOTE()
X_res, y_res = smote.fit_resample(X_train, y_train)
mitigated_model = XGBClassifier().fit(X_res, y_res)
# Re-run metrics to prove mitigation effect
```

---

## Commands

```bash
# Goal-oriented research
python main.py --goal "Prove that transformer models outperform RNNs for NLP"

# Deep-dive report
python main.py --report --topic "Recent advances in quantum error correction"

# With options
python main.py --goal "..." --claims claims.json --iterations 8 --threshold 0.85

# Web GUI (FastAPI + WebSocket at http://127.0.0.1:8000)
python run_gui.py

# React frontend dev server (proxies to backend)
cd gui/frontend && npm install && npm run dev

# Run individual agents
python -m agents.cross_validation_agent
python -m agents.flaw_detection_agent
python -m orchestration.continuous_research_loop --help

# Run tests
pytest
```

## Continuous Research Loop

Each iteration follows **DISCOVER → PLAN → ACT → OBSERVE → REFLECT**:

| Phase | What happens |
|-------|-------------|
| **DISCOVER** | Load and validate claims; run autonomy self-check |
| **PLAN** | Derive research queries from claims + memory gaps |
| **ACT** | Verify claims (code) → retrieve papers → cross-validate → detect flaws |
| **OBSERVE** | Compute `verified_ratio`; check for blocking flaws |
| **REFLECT** | Persist findings to MemoryStore; evolve prompts (SEPL); compact memory |

**Convergence** is declared when `verified_ratio ≥ converge_threshold` (default `0.90`) **and** no flaws above `flaw_halt_severity` (default `critical`) remain, or when `max_iterations` (default `10`) is reached.

Key outputs: `outputs/cross_validation_report.json`, `outputs/flaw_report.json`, `outputs/research_loop_report.json`.

---

## Architecture

### Bias Audit Pipeline

```mermaid
flowchart TB
    Start(["Start Pipeline"]) --> Det["Detection Agent"]
    Det --> J1{"Judge"}
    J1 -->|"Pass"| Mit["Mitigation Agent"]
    J1 -->|"Fail (new seed)"| Det
    J1 -->|"3 Failures"| Fail(["Pipeline Failed"])
    Mit --> J2{"Judge"}
    J2 -->|"Pass"| Aud["Auditing Agent"]
    J2 -->|"Fail (new seed)"| Mit
    J2 -->|"3 Failures"| Fail
    Aud --> FC["Format Check"]
    FC --> J3{"Judge"}
    J3 -->|"Pass"| Res["Research Phase"]
    J3 -->|"Claims Issue"| VerCheck["Verification Agent"]
    VerCheck --> Rev["Revision Agent"]
    Rev -->|"Re-evaluate"| J3
    J3 -->|"Fail (retry)"| Aud
    J3 -->|"3 Failures"| Fail
    Res --> RA["Research Agent"]
    Res --> GC["Gap Check"]
    Res --> Cov["Coverage Agent"]
    Res --> Rep["Reproducibility"]
    RA --> Mem["Memory Agent"]
    GC --> Mem
    Cov --> Mem
    Rep --> Mem
    Mem --> Opt["Optimizer Agent"]
    Opt --> Done(["Pipeline Complete"])
    Opt -.->|"Refined prompts (next run)"| Start
    style Start fill:#2E7D32,color:#fff
    style Done fill:#2E7D32,color:#fff
    style Fail fill:#C62828,color:#fff
    style J1 fill:#E65100,color:#fff
    style J2 fill:#E65100,color:#fff
    style J3 fill:#E65100,color:#fff
    style Rev fill:#1565C0,color:#fff
    style VerCheck fill:#1565C0,color:#fff
    style FC fill:#6A1B9A,color:#fff
    style Opt fill:#00695C,color:#fff
    style Mem fill:#00695C,color:#fff
```

**Execution model:** Agents run as subprocesses (`python -m agents.detection_agent 42`). The orchestrator does not modify agent code; it controls invocation order, seed, and retry count.

### Continuous Research Loop

```mermaid
flowchart TB
    Claims(["Claims / idea_input.json"]) --> SC["Self-Check (DISCOVER)"]
    SC --> Plan["Query Generation (PLAN)"]
    Plan --> Ver["Verification Agent (code)"]
    Ver --> RA["Research Agent (papers)"]
    RA --> CV["Cross-Validation Agent"]
    CV --> FD["Flaw Detection Agent"]
    FD --> Obs{{"OBSERVE: verified_ratio ≥ threshold\nAND no blocking flaws?"}}
    Obs -->|"Yes"| Done(["Converged ✓"])
    Obs -->|"No, iterations left"| Ref["REFLECT: persist → SEPL → compact"]
    Ref --> Plan
    Obs -->|"Max iterations"| Report(["Loop Report"])
    style Claims fill:#2E7D32,color:#fff
    style Done fill:#2E7D32,color:#fff
    style Report fill:#E65100,color:#fff
    style Obs fill:#1565C0,color:#fff
```

---

## Project Structure

```
Autonomous-Research-System/
├── main.py                   # CLI entry point (bias pipeline or research loop)
├── run_gui.py                # GUI entry point (web dashboard)
│
├── agents/                   # All agent modules
│   ├── detection_agent.py          # Bias detection (baseline models, fairness metrics)
│   ├── mitigation_agent.py         # Bias mitigation (SMOTE, threshold adjustment)
│   ├── auditing_agent.py           # Paper generation (sections, LaTeX, PDF)
│   ├── judge_agent.py              # Quality evaluation (rule-based + Gemini)
│   ├── revision_agent.py           # Applies Judge feedback to paper
│   ├── verification_agent.py       # Code-based claim verification
│   ├── research_agent.py           # alphaXiv/arXiv research for claims
│   ├── cross_validation_agent.py   # Cross-validate claims vs retrieved papers
│   ├── flaw_detection_agent.py     # Detect logical/statistical/methodological flaws
│   ├── self_check_agent.py         # Autonomy diagnostics (DISCOVER/PLAN/ACT/OBSERVE/REFLECT)
│   ├── idea_input_agent.py         # Parse uploaded research ideas (multimodal)
│   ├── gap_check_agent.py          # Paper vs reference PDF coverage
│   ├── coverage_agent.py           # Finds papers for gaps
│   ├── topic_coverage_agent.py     # Verifies topic comprehensiveness
│   ├── reproducibility_agent.py    # Reproducibility validation
│   ├── claim_comparison_agent.py   # Compares literature vs our claims
│   ├── format_check_agent.py       # Validates output tables/JSON/LaTeX format
│   ├── optimizer_agent.py          # Prompt refinement from memory
│   └── memory_agent.py             # SQLite-backed self-learning persistence
│
├── orchestration/            # Pipeline orchestration
│   ├── orchestrator.py                    # Main pipeline + Judge loop + retries
│   ├── continuous_research_loop.py        # Iterative claims → verify → retrieve → evolve
│   ├── research_orchestrator.py           # Coordinates research phases
│   ├── continuous_runner.py               # Background process manager
│   ├── idea_verification_orchestrator.py  # Idea submission workflow
│   └── sep_layer.py                       # Self-evolution protocol (SEPL)
│
├── runtime/                  # Unified execution engine
│   └── core.py               # PipelineRuntime, RuntimeConfig, RuntimeSummary
│
├── utils/                    # Shared utilities
│   ├── schemas.py                  # Dataclass I/O contracts (ModelMetrics, BaselineResults, …)
│   ├── llm_client.py               # Gemini API wrapper
│   ├── context.py                  # PipelineContext (shared state across agents)
│   ├── events.py                   # EventBus for pub/sub agent communication
│   ├── config_loader.py            # Loads prompts/rules from configs/
│   ├── claims_loader.py            # Parse claims from JSON, text, or idea_input.json
│   ├── claims_utils.py             # Claims manipulation utilities
│   ├── query_generator.py          # Generate research queries dynamically
│   ├── latex_generator.py          # LaTeX paper (IEEE/CUCAI 2026 format)
│   ├── research_client.py          # alphaXiv/arXiv/Semantic Scholar integration
│   ├── research_result_processor.py
│   ├── citations_helper.py
│   ├── citation_enrichment.py
│   ├── paper_quality_guardrail.py
│   ├── pdf_source_extractor.py
│   ├── structure_review.py         # Structure review, citation research
│   └── resource_registry.py
│
├── gui/                      # Web dashboard
│   ├── server.py             # FastAPI + WebSocket
│   ├── streaming_orchestrator.py
│   └── static/               # index.html, app.js
│
├── configs/                  # Declarative configuration
│   ├── pipeline.yaml         # Pipeline agent order, judge thresholds, research loop settings
│   ├── prompts/              # Gemini prompt templates
│   └── rules/                # Consistency rules (JSON)
│
├── docs/                     # Documentation
│   ├── ALPHAXIV_SETUP.md
│   ├── ARXIV_MCP_SETUP.md
│   ├── RESEARCH_CHECKLIST.md
│   └── SELF_EVOLUTION_ROADMAP.md
│
├── outputs/                  # Generated artifacts (created at runtime)
│   ├── paper/                # paper.tex, paper.pdf, references.bib
│   ├── paper_sections/       # Individual LaTeX sections
│   ├── figures/              # Publication-ready figures
│   ├── memory/               # memory.db (SQLite knowledge base)
│   ├── baseline_results.json
│   ├── mitigation_results.json
│   ├── cross_validation_report.json
│   ├── flaw_report.json
│   ├── research_loop_report.json
│   └── structure_review.json
│
├── tests/                    # Test suite
│   ├── runtime/              # Runtime contract tests
│   ├── gui/                  # GUI tests
│   ├── integration/          # End-to-end integration tests
│   └── fixtures/
│
├── requirements.txt
├── README.md
├── SETUP.md
├── authors.txt
├── .env.example
└── kaggle.json.example
```

---

## Components

### Runtime (`runtime/core.py`)

- **Role:** Unified execution engine for both pipeline modes.
- **Key classes:** `RuntimeConfig` (loaded from `configs/pipeline.yaml`), `PipelineRuntime` (runs agents, manages retries, emits events), `RuntimeSummary` (structured results).
- **Integrates:** `PipelineContext`, `EventBus`, typed schemas from `utils/schemas.py`.

### Orchestrator (`orchestration/orchestrator.py`)

- **Role:** Central controller for the bias audit pipeline. Runs agents in order, calls Judge, handles retries.
- **Constants:** `MAX_RETRIES = 3`, core agents: detection → mitigation → auditing; research agents run afterwards.
- **Key functions:**
  - `run_agent(agent_name, seed)` — subprocess `python -m agents.<module> <seed>`
  - `run_judge(agent_name)` — imports and calls `agents.judge_agent.evaluate(agent_name)`
- **Exit:** `sys.exit(1)` if any agent fails after all retries.

### Continuous Research Loop (`orchestration/continuous_research_loop.py`)

- **Role:** Domain-agnostic iterative research. Loads claims, runs DISCOVER→PLAN→ACT→OBSERVE→REFLECT until convergence.
- **Key function:** `run_research_loop(claims_source, goal, max_iterations, converge_threshold, …) → dict`
- **Convergence:** `verified_ratio ≥ converge_threshold` **and** no blocking flaws.
- **Self-evolution:** SEPL prompt evolution every `evolve_every` iterations; memory compaction every `compact_every` iterations.

### Judge Agent (`agents/judge_agent.py`)

- **Role:** Evaluate agent outputs. Return `{passed, feedback[], retry_hint}`.
- **Modes:**
  - **Rule-based (always):** File existence, schema, section names, table presence.
  - **Gemini (when `GOOGLE_API_KEY` set):** Semantic evaluation of quality, consistency, claim support.
- **API:** `evaluate(agent_name)`, `evaluate_all()`
- **CLI:** `python -m agents.judge_agent [detection|mitigation|auditing]`

### Detection Agent (`agents/detection_agent.py`)

- **Role:** Download Credit Card Fraud dataset, inject synthetic protected attribute, train baseline models, compute fairness metrics.
- **Input:** Kaggle dataset `mlg-ulb/creditcardfraud` (via kagglehub)
- **Output:** `data_splits.npz`, `baseline_results.json`, `figures/fig_baseline_*.{png,pdf}`
- **CLI:** `python -m agents.detection_agent [seed]`

### Mitigation Agent (`agents/mitigation_agent.py`)

- **Role:** Load Detection outputs, apply SMOTE, train XGBoost, apply threshold adjustment, produce comparative matrix and asymmetric cost analysis.
- **Input:** `data_splits.npz`, `baseline_results.json`
- **Output:** `mitigation_results.json`, `mitigation_comparison.png`, `figures/fig_mitigation_comparison.{png,pdf}`
- **CLI:** `python -m agents.mitigation_agent [seed]`

### Auditing Agent (`agents/auditing_agent.py`)

- **Role:** Generate paper sections from templates + Detection/Mitigation JSON, compile draft, generate LaTeX, run structure review.
- **Input:** `baseline_results.json`, `mitigation_results.json`
- **Output:** `paper_sections/*.tex`, `paper/paper.tex`, `paper/paper.pdf`, `structure_review.json`
- **CLI:** `python -m agents.auditing_agent`

### Cross-Validation Agent (`agents/cross_validation_agent.py`)

- **Role:** Cross-validate claims against retrieved papers; assigns verdict: `support | contradict | neutral` per claim.
- **Input:** Claims list + `research_findings.json` (or loads from disk).
- **Output:** `outputs/cross_validation_report.json`; persists verdicts to MemoryStore.
- **CLI:** `python -m agents.cross_validation_agent`

### Flaw Detection Agent (`agents/flaw_detection_agent.py`)

- **Role:** Three-pass flaw detection — literature contradictions, code-verification failures, Gemini semantic analysis against known pitfalls.
- **Severity levels:** `critical | high | medium | low`
- **Output:** `outputs/flaw_report.json`; persists new critical/high flaws as pitfalls in MemoryStore.
- **CLI:** `python -m agents.flaw_detection_agent`

### Memory Agent (`agents/memory_agent.py`)

- **Role:** SQLite-backed self-learning persistence at `outputs/memory/memory.db`.
- **Pipeline tables:** `runs`, `agent_runs`, `metrics`, `verifications`, `idea_sessions`, `idea_insights`
- **Research loop tables:**

  | Table | Purpose |
  |-------|---------|
  | `research_goals` | Tracks goal text, iteration, status (`active`/`achieved`) |
  | `knowledge_entries` | Cross-validated findings: claim, verdict, confidence, supporting papers |
  | `pitfalls` | Known failure modes; frequency-counted; auto-populated by `flaw_detection_agent` |
  | `effective_methods` | Methods that worked; auto-populated by research loop on verified claims |

- **Key APIs:** `persist_run()`, `log_research_goal()`, `add_knowledge()`, `add_pitfall()`, `add_effective_method()`, `get_known_pitfalls()`, `get_effective_methods()`, `get_relevant_knowledge()`, `research_journey_summary()`

### LLM Client (`utils/llm_client.py`)

- **Role:** Gemini API wrapper for all agents.
- **Config:** `GOOGLE_API_KEY` or `GEMINI_API_KEY`, `GEMINI_MODEL` (default: `gemini-3.1-pro-preview`), `GEMINI_FALLBACK_MODEL` (default: `gemini-2.5-pro`)
- **Features:** `generate()`, `generate_with_grounding()` (Google Search), `generate_json()`
- **Optional:** Loads `.env` via `python-dotenv` if installed.

### Schemas (`utils/schemas.py`)

- **Role:** Typed dataclass contracts between agents. Replaces implicit dict I/O.
- **Key types:** `ModelMetrics`, `BaselineResults`, `MitigationResults`, `JudgeResult`, `AgentRunRecord`, `VerificationRecord`
- **No external dependencies** — stdlib only.

### LaTeX Generator (`utils/latex_generator.py`)

- **Role:** Generate publication-ready LaTeX paper in **IEEE/CUCAI 2026 format** (IEEEtran, two-column, IEEE-style citations) with figures, formulas (SPD, DI, EOD, Accuracy, F1), tables, bibliography.
- **Output:** `outputs/paper/paper.tex`, `outputs/paper/paper.pdf` (if pdflatex installed)

### Structure Review (`utils/structure_review.py`)

- **Role:** Review paper structure, verify formulas, run citation research via Gemini + Google Search grounding.
- **Output:** `outputs/structure_review.json`

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

### Structure Review

- **Structure review:** Verifies required sections (Background, Use Case, Detection, Mitigation, Audit, Discussion) and formulas (Demographic Parity, Disparate Impact, Equalized Odds, Accuracy, F1).
- **Citation research:** Uses Gemini with Google Search grounding to find recent (2023–2025) papers supporting the claims.

**Setup:** See [SETUP.md](SETUP.md). Model override: `GEMINI_MODEL=gemini-2.5-flash` (default: `gemini-3.1-pro-preview`).

---

## ArXiv MCP (Optional)

For Cursor chat: search and read arXiv papers via [arxiv-mcp-server](https://github.com/blazickjp/arxiv-mcp-server).

```bash
uv tool install arxiv-mcp-server
```

Add to `.cursor/mcp.json` (see `.cursor/mcp.json.example`). See [docs/ARXIV_MCP_SETUP.md](docs/ARXIV_MCP_SETUP.md).

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

### Bias Audit Pipeline

| Location | Variable | Default | Purpose |
|----------|----------|---------|---------|
| `orchestration/orchestrator.py` | `MAX_RETRIES` | 3 | Max attempts per agent |
| `agents/judge_agent.py` | `MIN_DETECTION_MODELS` | 2 | Required baseline count |
| `agents/judge_agent.py` | `MIN_MITIGATION_STRATEGIES` | 2 | Required mitigation count |
| `agents/judge_agent.py` | `MIN_PAPER_LENGTH` | 2000 | Min draft chars |
| `agents/judge_agent.py` | `REQUIRED_PAPER_SECTIONS` | [...] | Section names |
| `utils/llm_client.py` | `GEMINI_MODEL` | `gemini-3.1-pro-preview` | Gemini model |
| `utils/llm_client.py` | `GOOGLE_API_KEY` | env | API key |

### Continuous Research Loop (`configs/pipeline.yaml → research_loop`)

| Key | Default | Purpose |
|-----|---------|---------|
| `max_iterations` | `10` | Max loop iterations |
| `converge_threshold` | `0.90` | Fraction of verified claims required |
| `evolve_every` | `2` | Run SEPL prompt evolution every N iterations |
| `compact_every` | `3` | Compact memory every N iterations |
| `flaw_halt_severity` | `critical` | Severity blocking convergence (`critical\|high\|any\|none`) |

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
python main.py
```

### Running with GUI

A web dashboard streams live logs, metrics, figures, paper sections, and Judge feedback. On success, the research paper (PDF or Markdown) opens automatically.

```bash
python run_gui.py
```

Open http://127.0.0.1:8000 in your browser, then click **Run Pipeline**. The CLI (`python main.py`) remains available for headless runs.

### Individual Agents

```bash
python -m agents.detection_agent [seed]   # default seed=42
python -m agents.mitigation_agent [seed]
python -m agents.auditing_agent
python -m agents.judge_agent [detection|mitigation|auditing]
python -m agents.judge_agent               # evaluate all
python -m agents.cross_validation_agent   # cross-validate claims vs papers
python -m agents.flaw_detection_agent     # detect flaws in claims/findings
```

### Continuous Research Loop

```bash
# Use outputs/idea_input.json as claims source
python main.py --research

# Specify claims file, goal, and options
python main.py --research --claims claims.json --goal "My research goal" --iterations 8

# Full options
python main.py --research \
  --claims claims.json \
  --goal "Verify fairness mitigation claims" \
  --iterations 10 \
  --threshold 0.9 \
  --flaw-halt critical

# Run the loop module directly
python -m orchestration.continuous_research_loop --help
```

### Optional Setup

- **Kaggle:** For dataset download. See [SETUP.md](SETUP.md).
- **LaTeX:** For PDF compilation. See [SETUP.md](SETUP.md).
- **Gemini API:** For semantic evaluation and citation research. See [SETUP.md](SETUP.md).

---

## Outputs

### Generalized Research Mode

| Path | Description |
|------|-------------|
| `outputs/research_report.json` | Comprehensive research report (JSON) |
| `outputs/research_context.json` | Serialized ResearchContext (optional checkpoint) |
| `outputs/memory/memory.db` | Session-scoped SQLite knowledge base |
| `~/.autonomous_research/cross_session_memory.db` | Long-term cross-session memory |

### Legacy Pipeline Mode

| Path | Description |
|------|-------------|
| `outputs/paper_draft.md` | Full paper (Markdown) |
| `outputs/paper_sections/*.md` | Individual sections |
| `outputs/paper/paper.tex` | LaTeX source |
| `outputs/paper/paper.pdf` | Compiled PDF (if pdflatex installed) |
| `outputs/figures/*.pdf` | Publication-ready figures |
| `outputs/baseline_results.json` | Detection metrics |
| `outputs/mitigation_results.json` | Mitigation metrics + asymmetric cost |
| `outputs/structure_review.json` | Structure review + citation research |
| `outputs/cross_validation_report.json` | Per-claim literature verdict (support/contradict/neutral) |
| `outputs/flaw_report.json` | Detected flaws with severity and suggested fixes |
| `outputs/research_loop_report.json` | Full research loop run summary |
| `outputs/memory/memory.db` | SQLite knowledge base (all pipeline + research loop tables) |

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

1. Create `agents/new_agent.py` with `main(seed=42)` (or `main()` if deterministic).
2. Add to `orchestration/orchestrator.py`: `module_map`, `AGENTS`.
3. Add `evaluate_new_agent()` in `agents/judge_agent.py` and register in `evaluate()`.
4. Define output contract and Judge criteria.

### Customizing Judge Criteria

Edit `agents/judge_agent.py`: `REQUIRED_KEYS_*`, `MIN_*`, `REQUIRED_PAPER_SECTIONS`, or add checks in `evaluate_*()`.

### Config File

Pipeline configuration is in `configs/pipeline.yaml`. Prompts are in `configs/prompts/`, rules in `configs/rules/`.

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
| LaTeX step appears stuck | Gemini API or pdflatex is slow | **Normal:** Gemini ~1–2 min, pdflatex ~30s. Wait. **If >5 min:** Check `GOOGLE_API_KEY`; run `python -m utils.latex_generator` standalone to isolate; Ctrl+C and re-run. |

---

## Quick Reference

```bash
# Bias audit pipeline
python main.py

# Continuous research loop
python main.py --research
python main.py --research --claims claims.json --goal "My goal" --iterations 8

# GUI dashboard
python run_gui.py

# Individual pipeline agents
python -m agents.detection_agent [seed]
python -m agents.mitigation_agent [seed]
python -m agents.auditing_agent

# Judge only
python -m agents.judge_agent [detection|mitigation|auditing]
python -m agents.judge_agent   # evaluate all

# Research loop agents
python -m agents.cross_validation_agent
python -m agents.flaw_detection_agent
python -m orchestration.continuous_research_loop --help

# Run tests
pytest
```

See [SETUP.md](SETUP.md) for venv, Kaggle, LaTeX, and Gemini setup.
