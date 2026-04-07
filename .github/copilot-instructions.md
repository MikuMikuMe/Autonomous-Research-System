# Copilot Instructions

## Project Overview

This is the **Autonomous Research System** — a general-purpose, self-evolving multi-agent platform that autonomously researches, cross-validates claims, detects flaws, learns from past trials, and evolves toward quantifiable results. Two modes: **goal-oriented** (iterative convergence) and **report** (deep-dive).

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
pytest tests/test_memory_agent.py::test_recommend_seed_avoids_attempted_and_failed_history

# Install dependencies (Python 3.10+ required)
pip install -r requirements.txt
```

No linter or formatter is configured.

## Architecture

### Research Loop (Orchestrated in `orchestration/continuous_research_loop.py`)

The core engine is an iterative DISCOVER → PLAN → ACT → OBSERVE → REFLECT loop:

```
DISCOVER: load claims → self-check
  └─ Loop (max_iterations or convergence):
       PLAN:    derive research queries from claims + memory gaps
       ACT:     verify_agent (code) → research_agent (papers) →
                cross_validation_agent → flaw_detection_agent
       OBSERVE: compute verified_ratio; check for blocking flaws
       REFLECT: persist to MemoryStore → SEPL (prompt evolution) → memory compaction
  └─ Terminate when verified_ratio ≥ threshold AND no critical flaws
```

**Convergence**: `verified_ratio ≥ converge_threshold` (default 0.90) and no flaws above `flaw_halt_severity` (default `critical`). Self-evolves via SEPL every `evolve_every` iterations.

### Key Components

| Component | Location | Role |
|---|---|---|
| CLI Entry Point | `main.py` | Two modes: `--goal` and `--report --topic` |
| Research Loop | `orchestration/continuous_research_loop.py` | Core iterative research engine |
| Runtime | `runtime/core.py` | `ResearchRuntime`, `RuntimeConfig`, `RuntimeSummary` |
| Orchestrator | `orchestration/orchestrator.py` | CLI orchestrator with event printing |
| Schemas | `utils/schemas.py` | `ClaimVerdict`, `FlawRecord`, `ResearchIterationResult`, `VerificationRecord`, `RunRecord` |
| LLM Base | `utils/llm_base.py` | `BaseLLMClient` ABC, `GeminiClient`, `OpenAIClient`, `AnthropicClient`, provider registry |
| LLM Client | `utils/llm_client.py` | Backward-compat wrapper: `generate()`, `generate_json()`, `generate_with_grounding()` |
| Memory | `agents/memory_agent.py` | SQLite-backed `MemoryStore` — knowledge, pitfalls, effective methods, research goals |
| Cross-Validation | `agents/cross_validation_agent.py` | Cross-validate claims against papers; verdict: support/contradict/neutral |
| Flaw Detection | `agents/flaw_detection_agent.py` | Detect logical, statistical, methodological flaws |
| Sandbox | `utils/sandbox.py` | Hardened code execution for LLM-generated verification code |
| Tracing | `utils/tracing.py` | OpenTelemetry distributed tracing with lightweight fallback |
| Context | `utils/context.py` | `ResearchContext` with `ResearchMode` enum, `ClaimState` tracking |
| EventBus | `utils/events.py` | Typed event dispatch with WebSocket bridge |
| Config Loader | `utils/config_loader.py` | Lazy-loaded, cached prompts and rules |
| SEPL | `orchestration/sep_layer.py` | Self-Evolution Protocol Layer for prompt evolution |
| GUI Server | `gui/server.py` | FastAPI + WebSocket streaming API |
| GUI Frontend | `gui/frontend/` | React + TypeScript + Tailwind CSS (Vite) |
| Streaming Orch | `gui/streaming_orchestrator.py` | Background research execution for GUI |

### Memory — MemoryStore Tables

| Table | Purpose |
|---|---|
| `research_goals` | Tracks goal text, current iteration, status (`active`/`achieved`) |
| `knowledge_entries` | Cross-validated findings: claim, verdict, confidence, supporting papers |
| `pitfalls` | Known failure modes; frequency-counted; auto-populated by `flaw_detection_agent` |
| `effective_methods` | Methods that worked; auto-populated on verified claims |

Key APIs: `log_research_goal`, `add_knowledge`, `add_pitfall`, `add_effective_method`, `get_known_pitfalls`, `get_effective_methods`, `get_relevant_knowledge`, `research_journey_summary`.

### Output Artifacts (`outputs/`)

- `research_loop_report.json` — Full research loop run summary
- `cross_validation_report.json` — Per-claim literature verdict (support/contradict/neutral)
- `flaw_report.json` — Detected flaws with severity and suggested fixes
- `verification_report.json` — Code-based verification results
- `research_findings.json` — Retrieved papers and findings
- `research_context.json` — Serialized ResearchContext state
- `outputs/memory/memory.db` — SQLite knowledge base

## Key Conventions

### Agent Structure
Every agent has a callable `main()` and a CLI entry point:
```python
if __name__ == "__main__":
    main()
```

### Progress Markers for GUI Streaming
Agents emit structured progress lines consumed by the WebSocket stream:
```python
print(f"[QMIND_PROGRESS]{pct:.2f}|{label}")
```

### Schema-Validated I/O
Agents read/write outputs using dataclasses from `utils/schemas.py`, serialized to JSON.

### Configuration
- Research loop settings, mode overrides, LLM priority: `configs/pipeline.yaml`
- Prompt templates: `configs/prompts/` (loaded lazily by `config_loader.py`)
- Override LLM: `LLM_PROVIDER=openai python main.py` or `GEMINI_MODEL=gemini-2.5-flash python main.py`

### Imports
Use absolute imports from the project root. Each module resolves `PROJECT_ROOT` locally:
```python
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
```
`from __future__ import annotations` is used throughout for PEP 563 postponed evaluation.

### Environment Variables
- `GOOGLE_API_KEY` — Gemini API key (primary LLM provider)
- `OPENAI_API_KEY` — OpenAI API key (alternative provider)
- `ANTHROPIC_API_KEY` — Anthropic API key (alternative provider)
- `LLM_PROVIDER` — Force a specific provider: `gemini`, `openai`, `anthropic`
- `GEMINI_MODEL` — Override the default Gemini model
- `ALPHAXIV_TOKEN` — alphaXiv token for paper retrieval (optional)
- `OTEL_EXPORTER_OTLP_ENDPOINT` — OpenTelemetry collector endpoint (optional)

### Tests
Tests use pytest with fixtures in `tests/conftest.py`. Test files use `# pyright: reportAny=false` to suppress type warnings — don't add strict type checking there.
