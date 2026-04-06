"""
Config Loader — Lazy-loading prompts and rules from configs/.

Prompt templates and rules are loaded on first access and cached,
reducing memory overhead when many templates exist (progressive skill loading).
"""

from __future__ import annotations

import json
import os
import threading
from typing import Any

CONFIGS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "configs")
PROMPTS_DIR = os.path.join(CONFIGS_DIR, "prompts")
RULES_DIR = os.path.join(CONFIGS_DIR, "rules")

# Thread-safe caches for lazy loading
_prompt_cache: dict[str, str] = {}
_rules_cache: dict[str, dict | None] = {}
_cache_lock = threading.Lock()


def load_prompt(name: str, **kwargs) -> str:
    """
    Load a prompt template from configs/prompts/{name}.txt and format with kwargs.
    Templates are cached after first load (lazy/progressive loading).
    Returns the formatted string, or empty string if file not found.
    """
    with _cache_lock:
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
    Load a rules file from configs/rules/{name}.json.
    Cached after first load. Returns the parsed dict, or None if not found.
    """
    with _cache_lock:
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


def load_pipeline_config() -> dict[str, Any]:
    """Load and cache the main pipeline.yaml configuration."""
    with _cache_lock:
        if "__pipeline__" not in _rules_cache:
            try:
                import yaml
                path = os.path.join(CONFIGS_DIR, "pipeline.yaml")
                if os.path.exists(path):
                    with open(path, encoding="utf-8") as f:
                        _rules_cache["__pipeline__"] = yaml.safe_load(f) or {}
                else:
                    _rules_cache["__pipeline__"] = {}
            except Exception:
                _rules_cache["__pipeline__"] = {}
    return _rules_cache["__pipeline__"] or {}


def invalidate_cache(name: str | None = None) -> None:
    """Clear cached templates/rules. None = clear all."""
    with _cache_lock:
        if name is None:
            _prompt_cache.clear()
            _rules_cache.clear()
        else:
            _prompt_cache.pop(name, None)
            _rules_cache.pop(name, None)
