"""
Memory Agent — Persist session outcomes for self-evolution (Remember).

Design: After each pipeline run, persist (agent, outcome, feedback, timestamp) to
outputs/memory/session_*.json. Enables Optimizer to propose prompt/solution updates.
"""

import os
import json
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEMORY_DIR = os.path.join(PROJECT_ROOT, "outputs", "memory")
os.makedirs(MEMORY_DIR, exist_ok=True)


def persist_event(agent: str, outcome: str, feedback: list | str | None = None, data_snapshot: dict | None = None):
    """
    Persist a single event (agent run, judge result, etc.) to memory.
    outcome: "passed" | "failed" | "revised"
    feedback: list of strings or single string (Judge feedback, etc.)
    """
    event = {
        "timestamp": datetime.now().isoformat(),
        "agent": agent,
        "outcome": outcome,
        "feedback": feedback if isinstance(feedback, list) else ([feedback] if feedback else []),
        "data_snapshot": data_snapshot,
    }
    fname = f"event_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{agent}.json"
    path = os.path.join(MEMORY_DIR, fname)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(event, f, indent=2)
    return path


def persist_session(results: dict, judge_failures: list | None = None):
    """
    Persist full pipeline session summary.
    results: {agent_name: {passed, attempts, feedback?}}
    judge_failures: list of (agent, feedback) for failed judges
    """
    session = {
        "timestamp": datetime.now().isoformat(),
        "results": results,
        "judge_failures": judge_failures or [],
        "all_passed": all(r.get("passed", False) for r in results.values()),
    }
    fname = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    path = os.path.join(MEMORY_DIR, fname)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(session, f, indent=2)
    return path


def load_recent_sessions(limit: int = 10) -> list[dict]:
    """Load most recent session files for Optimizer."""
    if not os.path.exists(MEMORY_DIR):
        return []
    files = sorted(
        [f for f in os.listdir(MEMORY_DIR) if f.startswith("session_") and f.endswith(".json")],
        reverse=True,
    )[:limit]
    out = []
    for f in files:
        try:
            with open(os.path.join(MEMORY_DIR, f), encoding="utf-8") as fp:
                out.append(json.load(fp))
        except (json.JSONDecodeError, OSError):
            pass
    return out


def load_recent_events(agent: str | None = None, limit: int = 20) -> list[dict]:
    """Load recent events, optionally filtered by agent."""
    if not os.path.exists(MEMORY_DIR):
        return []
    files = sorted(
        [f for f in os.listdir(MEMORY_DIR) if f.startswith("event_") and f.endswith(".json")],
        reverse=True,
    )[:limit * 2]
    out = []
    for f in files:
        if agent and agent not in f:
            continue
        try:
            with open(os.path.join(MEMORY_DIR, f), encoding="utf-8") as fp:
                out.append(json.load(fp))
        except (json.JSONDecodeError, OSError):
            pass
        if len(out) >= limit:
            break
    return out
