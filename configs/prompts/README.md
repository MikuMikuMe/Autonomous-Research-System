# Config-Driven Prompts

Prompts are loaded from this directory. Placeholders use Python format syntax: `{name}`.

- `trade_off_summary.txt` — Asymmetric cost analysis paragraph (mitigation_agent)
- `mitigation_claims.txt` — Intro/summary/XGBoost claims from data (auditing_agent)
- `revision.txt` — Paper revision from Judge feedback (revision_agent)
- `verification.txt` — Code generation for claim verification (verification_agent)

Fallback: When Gemini is unavailable, agents use minimal programmatic fallbacks (never hardcoded narrative that contradicts data).
