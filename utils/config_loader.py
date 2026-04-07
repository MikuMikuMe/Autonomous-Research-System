"""
Config Loader — Lazy-load prompts and rules from configs/.

Prompts and rules are loaded on-demand and cached in memory.
This reduces startup overhead when many templates exist.
"""

import os
import json
from functools import lru_cache

CONFIGS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "configs")
PROMPTS_DIR = os.path.join(CONFIGS_DIR, "prompts")
RULES_DIR = os.path.join(CONFIGS_DIR, "rules")

# Cache for loaded templates (cleared on reload)
_prompt_cache: dict[str, str] = {}
_rules_cache: dict[str, dict | None] = {}


def load_prompt(name: str, **kwargs) -> str:
    """
    Lazily load a prompt template from configs/prompts/{name}.txt and format with kwargs.
    Templates are cached after first load. Returns empty string if file not found.
    """
    if name not in _prompt_cache:
        path = os.path.join(PROMPTS_DIR, f"{name}.txt")
        if not os.path.exists(path):
            _prompt_cache[name] = ""
        else:
            with open(path, encoding="utf-8") as f:
                _prompt_cache[name] = f.read()

    template = _prompt_cache[name]
    if not template:
        return ""
    try:
        return template.format(**kwargs)
    except KeyError:
        return template


def load_rules(name: str) -> dict | None:
    """
    Lazily load a rules file from configs/rules/{name}.json.
    Rules are cached after first load. Returns None if not found.
    """
    if name not in _rules_cache:
        path = os.path.join(RULES_DIR, f"{name}.json")
        if not os.path.exists(path):
            _rules_cache[name] = None
        else:
            try:
                with open(path, encoding="utf-8") as f:
                    _rules_cache[name] = json.load(f)
            except (json.JSONDecodeError, OSError):
                _rules_cache[name] = None

    return _rules_cache[name]


@lru_cache(maxsize=1)
def load_pipeline_config() -> dict:
    """Load and cache the pipeline configuration from configs/pipeline.yaml."""
    path = os.path.join(CONFIGS_DIR, "pipeline.yaml")
    if not os.path.exists(path):
        return {}
    try:
        import yaml
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except (ImportError, Exception):
        return {}


def reload_caches() -> None:
    """Clear all cached templates and rules (useful for testing or hot-reload)."""
    _prompt_cache.clear()
    _rules_cache.clear()
    load_pipeline_config.cache_clear()


def list_available_prompts() -> list[str]:
    """List all available prompt template names (without extension)."""
    if not os.path.isdir(PROMPTS_DIR):
        return []
    return [
        f[:-4] for f in os.listdir(PROMPTS_DIR)
        if f.endswith(".txt")
    ]


def list_available_rules() -> list[str]:
    """List all available rule file names (without extension)."""
    if not os.path.isdir(RULES_DIR):
        return []
    return [
        f[:-5] for f in os.listdir(RULES_DIR)
        if f.endswith(".json")
    ]
