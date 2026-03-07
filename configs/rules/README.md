# Config Rules

Declarative rules for claim/data consistency. Used by agents and Optimizer to validate outputs.

- `claim_data_consistency.json` — Forbidden phrases and required framing when data contradicts default narrative.

Agents can load rules via `config_loader.load_rules(name)`.
