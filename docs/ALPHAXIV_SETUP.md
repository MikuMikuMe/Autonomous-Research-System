# alphaXiv & Research Pipeline Integration

The research pipeline uses **alphaXiv Assistant V2** (Chat API) when `ALPHAXIV_TOKEN` is set, with an automatic fallback to **arXiv + Semantic Scholar + Gemini** when alphaXiv is unavailable.

## Research Client (`research_client.py`)

| Backend | When used | Auth |
|---------|-----------|------|
| **alphaXiv Assistant V2** | `ALPHAXIV_TOKEN` set | Bearer API key |
| **arXiv + Semantic Scholar + Gemini** | Fallback (no token or alphaXiv fails) | None / `GOOGLE_API_KEY` |

## alphaXiv Assistant V2 Setup

1. **Get API key**
   - Sign in at [alphaxiv.org](https://alphaxiv.org/signin)
   - Obtain an API key from your account settings (API keys page)

2. **Configure `.env`**
   ```
   ALPHAXIV_TOKEN=your_api_key_here
   ```

3. **Optional:** Use dev API
   ```
   ALPHAXIV_ASSISTANT_URL=https://api-dev.alphaxiv.org/assistant/v2/chat
   ```

The Assistant V2 Chat API accepts natural language research questions and returns synthesized answers with deep research and thinking enabled.

## Fallback (arXiv + Semantic Scholar + Gemini)

When alphaXiv is not configured or fails, the pipeline uses:

- **arXiv** — Search and download PDFs (no auth)
- **Semantic Scholar** — Search 200M+ papers (no auth, optional API key for higher limits)
- **Gemini** — Synthesize answers from paper context (`GOOGLE_API_KEY` required)

Install: `pip install arxiv semanticscholar pypdf` (included in requirements.txt)

## Pipeline integration

The **unified orchestrator** (`python orchestrator.py`) runs the research phase automatically:

1. **Research Agent** — Queries research_client to prove claims from bias_mitigation.pdf, Bias Auditing Framework.pdf, Bias Detection findings.pdf
2. **Gap Check Agent** — Compares paper + research vs how_biases_are_introduced.pdf
3. **Coverage Agent** — Finds papers for gaps via research_client
4. **Reproducibility Agent** — Runs detection/mitigation with multiple seeds

Run the full pipeline:

```bash
python orchestrator.py
```

Run only the research phase: `python research_orchestrator.py`

## Cursor MCP (optional)

For Cursor chat integration, configure `.cursor/mcp.json` with alphaXiv MCP. The Python agents use the Assistant V2 API directly, which accepts API keys.
