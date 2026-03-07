# ArXiv MCP Server Setup

The project uses **arXiv + Semantic Scholar** for paper search and claim verification. For Cursor chat integration, you can enable the [arxiv-mcp-server](https://github.com/blazickjp/arxiv-mcp-server) so AI assistants can search and read arXiv papers directly.

## Install arxiv-mcp-server

```bash
uv tool install arxiv-mcp-server
```

## MCP Configuration

Copy `.cursor/mcp.json.example` to `.cursor/mcp.json` and add the arxiv-mcp-server:

```json
{
  "mcpServers": {
    "arxiv-mcp-server": {
      "command": "uv",
      "args": [
        "tool",
        "run",
        "arxiv-mcp-server",
        "--storage-path",
        "outputs/arxiv_papers"
      ]
    }
  }
}
```

**Note:** Use an absolute path for `--storage-path` if the relative path does not resolve. Example (Windows): `C:/path/to/QMIND-Agent/outputs/arxiv_papers`.

## Available Tools (when MCP enabled)

| Tool | Purpose |
|------|---------|
| `search_papers` | Query arXiv with filters (date, categories) |
| `download_paper` | Download paper by arXiv ID |
| `read_paper` | Read downloaded paper content |
| `list_papers` | List locally stored papers |

## Research Pipeline Integration

The **Python research pipeline** (`research_agent.py`, `research_client.py`) uses arXiv + Semantic Scholar directly (no MCP) for:

1. **Search** — Always searches arXiv + Semantic Scholar for papers
2. **Verify** — Extracts claims, verifies against our experimental data
3. **Compare** — Determines whose claim is more supported (our data vs literature)
4. **Cite** — Cites the paper whose claim is more supported

The MCP is for **Cursor chat agents** — when you ask Cursor to search for papers or analyze an arXiv paper, it can use the arxiv-mcp-server tools.

## Claim Comparison Flow

```
Query → Search (arXiv + Semantic Scholar) → Extract claims from papers
     → Verify against baseline_results.json, mitigation_results.json
     → Compare: our data vs literature — whose claim is more supported?
     → Verification agent verifies the conclusion
     → Cite the winning paper
```

Run claim comparison standalone:

```bash
python claim_comparison_agent.py "XGBoost with SMOTE achieves EU AI Act compliance"
```
