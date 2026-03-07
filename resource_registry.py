"""
RSPL — Resource Substrate Protocol Layer: Load and resolve versioned resources.

Design: Agents, tools, prompts, environments are registered in configs/resources/registry.json
with version and lifecycle. This module provides resolution and loading.
"""

import os
import json

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIGS_DIR = os.path.join(SCRIPT_DIR, "configs")
REGISTRY_PATH = os.path.join(CONFIGS_DIR, "resources", "registry.json")


def load_registry() -> dict:
    """Load the resource registry. Returns empty dict if not found."""
    if not os.path.exists(REGISTRY_PATH):
        return {}
    try:
        with open(REGISTRY_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def get_agent(agent_id: str) -> dict | None:
    """Resolve agent by id. Returns {module, version, lifecycle} or None."""
    reg = load_registry()
    for a in reg.get("agents", []):
        if a.get("id") == agent_id:
            return a
    return None


def get_prompt(prompt_id: str) -> dict | None:
    """Resolve prompt by id. Returns {path, version} or None."""
    reg = load_registry()
    for p in reg.get("prompts", []):
        if p.get("id") == prompt_id:
            return p
    return None


def list_agents() -> list[str]:
    """List registered agent ids."""
    reg = load_registry()
    return [a.get("id") for a in reg.get("agents", []) if a.get("id")]


def list_prompts() -> list[str]:
    """List registered prompt ids."""
    reg = load_registry()
    return [p.get("id") for p in reg.get("prompts", []) if p.get("id")]
