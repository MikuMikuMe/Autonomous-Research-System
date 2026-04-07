# Autonomous Research System

A general-purpose, self-evolving multi-agent research platform. Give it a goal or topic — it automatically researches, cross-validates claims against literature, detects flaws, learns from past trials, and evolves toward quantifiable results.

## Two Modes

| Mode | Description | Convergence |
|------|-------------|-------------|
| **Goal-Oriented** | Iterative research toward a quantifiable goal. Loops until claims are verified. | `verified_ratio ≥ threshold` and no critical flaws |
| **Report / Deep-Dive** | Comprehensive research report on a topic with thorough literature review. | Minimum 5 iterations, lower threshold (0.70) |

## Quick Start

```bash
# Install dependencies (Python 3.10+)
pip install -r requirements.txt

# Goal-oriented research
python main.py --goal "Prove that transformer models outperform RNNs for time series"

# Deep-dive report
python main.py --report --topic "Recent advances in quantum error correction"

# With options
python main.py --goal "..." --claims claims.json --iterations 8 --threshold 0.85

# Web GUI (http://127.0.0.1:8000)
python run_gui.py

# React frontend dev server (requires backend running on :8000)
# Start backend first: python run_gui.py
cd gui/frontend && npm install && npm run dev
```

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `GOOGLE_API_KEY` | Yes | Google Gemini API key |
| `OPENAI_API_KEY` | No | OpenAI API key (alternative provider) |
| `ANTHROPIC_API_KEY` | No | Anthropic API key (alternative provider) |
| `LLM_PROVIDER` | No | Force a specific provider: `gemini`, `openai`, `anthropic` |
| `GEMINI_MODEL` | No | Override default Gemini model |
| `ALPHAXIV_TOKEN` | No | alphaXiv token for paper retrieval |

---

## Architecture

### Research Loop

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

### Multi-LLM Support

The system supports multiple LLM providers through a unified `BaseLLMClient` interface:

- **Gemini** (default) — Google Generative AI
- **OpenAI** — GPT-5 and compatible models
- **Anthropic** — Claude models

Provider selection: first available key wins, or specify via `LLM_PROVIDER` env var.

### Key Components

| Component | Location | Role |
|---|---|---|
| CLI Entry Point | `main.py` | Two modes: `--goal` and `--report` |
| Research Loop | `orchestration/continuous_research_loop.py` | Iterative claims → verify → retrieve → cross-validate → flaw-detect → evolve |
| Runtime | `runtime/core.py` | `ResearchRuntime`, `RuntimeConfig`, `RuntimeSummary` — structured execution |
| Orchestrator | `orchestration/orchestrator.py` | CLI-facing orchestrator with event printing |
| Schemas | `utils/schemas.py` | `ClaimVerdict`, `FlawRecord`, `ResearchIterationResult`, `VerificationRecord` |
| LLM Base | `utils/llm_base.py` | `BaseLLMClient` ABC, provider registry, smart routing |
| LLM Client | `utils/llm_client.py` | Backward-compat wrapper: `generate()`, `generate_json()`, `generate_with_grounding()` |
| Memory | `agents/memory_agent.py` | SQLite-backed store for knowledge, pitfalls, effective methods, research goals |
| Cross-Validation | `agents/cross_validation_agent.py` | Cross-validate claims against retrieved papers |
| Flaw Detection | `agents/flaw_detection_agent.py` | Detect logical, statistical, methodological flaws |
| Sandbox | `utils/sandbox.py` | Hardened code execution for LLM-generated verification code |
| Tracing | `utils/tracing.py` | OpenTelemetry distributed tracing with lightweight fallback |
| Config Loader | `utils/config_loader.py` | Lazy-loaded, cached prompts and rules |
| Context | `utils/context.py` | `ResearchContext` with `ResearchMode` enum, `ClaimState` tracking |
| EventBus | `utils/events.py` | Typed event dispatch with WebSocket bridge |
| SEPL | `orchestration/sep_layer.py` | Self-Evolution Protocol Layer for prompt evolution |
| GUI Server | `gui/server.py` | FastAPI + WebSocket streaming API |
| GUI Frontend | `gui/frontend/` | React + TypeScript + Tailwind CSS (Vite) |

### Memory — MemoryStore Tables

| Table | Purpose |
|---|---|
| `research_goals` | Tracks goal text, current iteration, status (`active`/`achieved`) |
| `knowledge_entries` | Cross-validated findings: claim, verdict, confidence, supporting papers |
| `pitfalls` | Known failure modes; frequency-counted; auto-populated by flaw detection |
| `effective_methods` | Methods that worked; auto-populated on verified claims |

Key APIs: `log_research_goal`, `add_knowledge`, `add_pitfall`, `add_effective_method`, `get_known_pitfalls`, `get_effective_methods`, `get_relevant_knowledge`, `research_journey_summary`.

---

## Web GUI

The system ships with a React frontend (`gui/frontend/`) and a FastAPI backend (`gui/server.py`).

### Running

```bash
# Production: build frontend and serve from backend
cd gui/frontend && npm install && npm run build
python run_gui.py    # serves at http://127.0.0.1:8000

# Development: Vite dev server with API proxy
python run_gui.py &  # backend on :8000
cd gui/frontend && npm run dev  # frontend on :5173, proxies /api and /ws to :8000
```

### Frontend Components

| Component | Purpose |
|---|---|
| `ResearchInput` | Mode selector (goal/report), goal textarea, advanced options |
| `ProgressTracker` | Real-time iteration progress, log streaming, convergence status |
| `ResultsViewer` | Tabbed view: report, cross-validation, flaws, verification |
| `MemoryExplorer` | Knowledge entries, pitfalls, research journey |
| `ProviderStatus` | Shows available LLM providers |
| `IdeaVerifier` | Submit ideas for iterative verification |

### API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/ws` | WebSocket | Real-time event streaming |
| `/api/research/start` | POST | Start a research session |
| `/api/outputs/research` | GET | Latest research loop report |
| `/api/outputs/cross_validation` | GET | Cross-validation results |
| `/api/outputs/flaws` | GET | Flaw detection report |
| `/api/outputs/verification` | GET | Verification report |
| `/api/providers` | GET | Available LLM providers |
| `/api/memory/journey` | GET | Research journey summary |
| `/api/memory/knowledge` | GET | Knowledge base entries |
| `/api/memory/pitfalls` | GET | Known pitfalls |
| `/api/idea/verify` | POST | Submit idea for verification |

---

## Configuration

All settings in `configs/pipeline.yaml`:

```yaml
research_loop:
  max_iterations: 10
  converge_threshold: 0.90
  evolve_every: 2
  compact_every: 3
  flaw_halt_severity: critical

modes:
  goal:
    max_iterations: 10
    converge_threshold: 0.90
  report:
    max_iterations: 5
    converge_threshold: 0.70

llm:
  priority: [gemini, openai, anthropic]
```

Prompt templates: `configs/prompts/`. Rules: `configs/rules/`.

---

## Outputs

All artifacts go to `outputs/`:

| File | Description |
|---|---|
| `research_loop_report.json` | Full research loop summary |
| `cross_validation_report.json` | Per-claim literature verdicts |
| `flaw_report.json` | Detected flaws with severity |
| `verification_report.json` | Code-based claim verification |
| `research_findings.json` | Retrieved research papers/findings |
| `coverage_suggestions.json` | Topic coverage analysis |
| `research_context.json` | Serialized `ResearchContext` state |
| `memory/memory.db` | SQLite knowledge base |

---

## Testing

```bash
pytest                         # all tests
pytest tests/test_memory_agent.py  # specific test file
pytest -k "test_name"          # specific test
```

---

## Project Structure

```
main.py                        CLI entry point (--goal / --report)
run_gui.py                     Launch web GUI
agents/
  memory_agent.py              SQLite-backed MemoryStore
  cross_validation_agent.py    Cross-validate claims vs papers
  flaw_detection_agent.py      Detect research flaws
  verification_agent.py        Code-based claim verification
  research_agent.py            Literature retrieval
  coverage_agent.py            Coverage analysis
  optimizer_agent.py           Research optimization
  self_check_agent.py          Self-diagnostics
  ...
orchestration/
  continuous_research_loop.py  Core iterative research engine
  orchestrator.py              CLI orchestrator
  sep_layer.py                 Self-Evolution Protocol Layer
  idea_verification_orchestrator.py
gui/
  server.py                    FastAPI + WebSocket backend
  streaming_orchestrator.py    Background research execution
  frontend/                    React + TypeScript + Tailwind (Vite)
    src/
      components/              ResearchInput, ProgressTracker, ResultsViewer, ...
      hooks/                   useWebSocket
      api.ts                   API client
runtime/
  core.py                      ResearchRuntime, RuntimeConfig
utils/
  llm_base.py                  Multi-LLM provider abstraction
  llm_client.py                Backward-compat LLM wrapper
  sandbox.py                   Hardened code execution
  tracing.py                   OpenTelemetry tracing
  context.py                   ResearchContext, ClaimState
  schemas.py                   Typed data contracts
  events.py                    EventBus with WebSocket bridge
  config_loader.py             Lazy prompt/rule loading
configs/
  pipeline.yaml                System configuration
  prompts/                     LLM prompt templates
  rules/                       Validation rules
tests/                         pytest test suite
```
