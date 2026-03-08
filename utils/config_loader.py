"""
Config Loader — Load prompts and rules from configs/ (never hardcode).
"""

import os
import json

CONFIGS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "configs")
PROMPTS_DIR = os.path.join(CONFIGS_DIR, "prompts")
RULES_DIR = os.path.join(CONFIGS_DIR, "rules")


def load_prompt(name: str, **kwargs) -> str:
    """
    Load a prompt template from configs/prompts/{name}.txt and format with kwargs.
    Returns the formatted string, or empty string if file not found.
    """
    path = os.path.join(PROMPTS_DIR, f"{name}.txt")
    if not os.path.exists(path):
        return ""
    with open(path, encoding="utf-8") as f:
        template = f.read()
    try:
        return template.format(**kwargs)
    except KeyError:
        return template


def load_rules(name: str) -> dict | None:
    """
    Load a rules file from configs/rules/{name}.json.
    Returns the parsed dict, or None if not found.
    """
    path = os.path.join(RULES_DIR, f"{name}.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None
