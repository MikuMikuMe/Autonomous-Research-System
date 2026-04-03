# Copilot Instructions

## Project Overview

This is the **Bias Audit Pipeline** — an autonomous multi-agent research system that detects, mitigates, and audits bias in financial AI (credit-card fraud detection models), producing an IEEE/CUCAI-format LaTeX research paper. The system is built around three core pipeline agents evaluated by a Judge, with a follow-up research verification phase.

## Commands

```bash
# Run the bias audit pipeline
python main.py

# Run the continuous research loop (new)
python main.py --research --claims claims.json --goal "My research goal" --iterations 8
python main.py --research                          # uses outputs/idea_input.json as claims

# Run individual research loop agents directly
python -m agents.cross_validation_agent            # cross-validate claims vs papers
python -m agents.flaw_detection_agent              # detect logical/statistical flaws
python -m orchestration.continuous_research_loop --help

# Run web dashboard (FastAPI + WebSocket at http://127.0.0.1:8000)
python run_gui.py

# Run individual pipeline agents directly
python -m agents.detection_agent [seed]     # default seed=42
python -m agents.mitigation_agent [seed]
python -m agents.auditing_agent
python -m agents.judge_agent [detection|mitigation|auditing]

# Run tests
pytest
pytest tests/test_memory_agent.py::test_recommend_seed_avoids_attempted_and_failed_history  # single test

# Install dependencies (Python 3.10+ required)
pip install -r requirements.txt
```

No linter or formatter is configured.

## Architecture

### Core Pipeline (Orchestrated in `orchestration/orchestrator.py`)

```
Detection Agent → Judge → Mitigation Agent → Judge → Auditing Agent → Judge → Research Phase
```

Each core agent runs as an **isolated subprocess** (`python -m agents.<module> <seed>`). If a Judge fails an agent, the orchestrator retries up to 3 times with an incremented seed (42 → 43 → 44). A different seed changes the synthetic protected attribute injection and train/test split.

After the paper passes the Judge, a **research phase** runs sequentially: `research_agent` → `gap_check_agent` → `coverage_agent` → `reproducibility_agent` → `verification_agent` → `optimizer_agent`.

### Continuous Research Loop (Orchestrated in `orchestration/continuous_research_loop.py`)

The second mode of operation — a **domain-agnostic, iterative research agent** driven by user-supplied claims:

```
DISCOVER: load claims → self-check
  └─ Loop (max_iterations or convergence):
       PLAN:    derive research queries from claims + memory gaps
       ACT:     verify_agent (code) → research_agent (papers) → cross_validation_agent → flaw_detection_agent
       OBSERVE: compute verified_ratio; check for blocking flaws
       REFLECT: persist to MemoryStore → SEPL (prompt evolution) → memory compaction
  └─ Terminate when verified_ratio ≥ converge_threshold AND no critical flaws
```

**Convergence** is declared when `verified_ratio ≥ converge_threshold` (default 0.90) and no flaws above `flaw_halt_severity` (default `critical`) remain. The loop self-evolves via SEPL every `evolve_every` iterations.

### Key Components

| Component | Location | Role |
|---|---|---|
| Orchestrator | `orchestration/orchestrator.py` | Runs bias pipeline, Judge loop, retry logic |
| Research Loop | `orchestration/continuous_research_loop.py` | Iterative claims → verify → retrieve → cross-validate → flaw-detect → evolve |
| Runtime | `runtime/core.py` | `PipelineRuntime`, `RuntimeConfig`, `RuntimeSummary` — structured execution state |
| Schemas | `utils/schemas.py` | Dataclass I/O contracts: `ModelMetrics`, `BaselineResults`, `MitigationResults`, `JudgeResult`, `AgentRunRecord` |
| Claims Loader | `utils/claims_loader.py` | Parse claims from JSON, text, or `idea_input.json` into `list[dict]` |
| LLM Client | `utils/llm_client.py` | Gemini API wrapper (lazy-loaded) |
| Memory | `agents/memory_agent.py` | SQLite-backed `MemoryStore` — persists agent history, Judge feedback, seed recommendations, research knowledge, pitfalls, effective methods |
| Cross-Validation | `agents/cross_validation_agent.py` | Cross-validate claims against retrieved papers; verdict: support/contradict/neutral |
| Flaw Detection | `agents/flaw_detection_agent.py` | Detect logical, statistical, methodological flaws; persist pitfalls to memory |
| GUI Server | `gui/server.py` | FastAPI + WebSocket streaming; `gui/streaming_orchestrator.py` wraps the core orchestrator |
| Config Loader | `utils/config_loader.py` | Loads `configs/pipeline.yaml` and prompt templates from `configs/prompts/` |

### Memory — extended MemoryStore tables

Beyond the original pipeline tables (`runs`, `agent_runs`, `metrics`, `verifications`), the research loop adds:

| Table | Purpose |
|---|---|
| `research_goals` | Tracks goal text, current iteration, status (`active`/`achieved`) |
| `knowledge_entries` | Cross-validated findings: claim, verdict, confidence, supporting papers |
| `pitfalls` | Known failure modes; frequency-counted; auto-populated by `flaw_detection_agent` |
| `effective_methods` | Methods that worked; auto-populated by `continuous_research_loop` on verified claims |

Key new APIs: `log_research_goal`, `add_knowledge`, `add_pitfall`, `add_effective_method`, `get_known_pitfalls`, `get_effective_methods`, `get_relevant_knowledge`, `research_journey_summary`.

### Agent Output Artifacts (`outputs/`)

- `baseline_results.json` — Detection agent output (consumed by Mitigation)
- `mitigation_results.json` — Mitigation agent output (consumed by Auditing)
- `outputs/paper/paper.tex`, `paper.pdf` — Final paper
- `outputs/paper_sections/` — Individual section files written by Auditing
- `outputs/figures/` — Matplotlib figures
- `structure_review.json` — Format/structure check output
- `cross_validation_report.json` — Per-claim literature verdict (support/contradict/neutral)
- `flaw_report.json` — Detected flaws with severity and suggested fixes
- `research_loop_report.json` — Full research loop run summary
- `outputs/memory/memory.db` — SQLite knowledge base (all tables above)

## Key Conventions

### Agent Structure
Every agent has a callable `main(seed=42)` (or `main()` for deterministic agents) and a CLI entry point:
```python
if __name__ == "__main__":
    import sys
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else 42
    main(seed=seed)
```

### Progress Markers for GUI Streaming
Agents emit structured progress lines consumed by the WebSocket stream:
```python
print(f"[QMIND_PROGRESS]{pct:.2f}|{label}")
```

### Schema-Validated I/O
Agents read/write outputs using dataclasses from `utils/schemas.py`, serialized to JSON. Always use these schemas rather than raw dicts for inter-agent data exchange.

### Configuration
- Pipeline order, retry count, memory settings: `configs/pipeline.yaml`
- Gemini prompt templates: `configs/prompts/` (loaded by `config_loader.py`)
- Judge thresholds are constants at the top of `agents/judge_agent.py`: `MIN_DETECTION_MODELS`, `MIN_MITIGATION_STRATEGIES`, `MIN_PAPER_LENGTH`, `REQUIRED_PAPER_SECTIONS`
- Override Gemini model at runtime: `GEMINI_MODEL=gemini-2.5-flash python main.py`

### Imports
Use absolute imports from the project root. Each module resolves `PROJECT_ROOT` locally:
```python
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
```
`from __future__ import annotations` is used throughout for PEP 563 postponed evaluation.

### Environment Variables
- `GOOGLE_API_KEY` — Gemini API key (required for LLM calls)
- `ALPHAXIV_TOKEN` — alphaXiv token for research phase (optional)
- `GEMINI_MODEL` — Override the default Gemini model

### Tests
Tests use pytest with fixtures in `tests/conftest.py`. Test files use `# pyright: reportAny=false` to suppress type warnings — don't add strict type checking there.
