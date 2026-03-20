from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import cast

from agents.memory_agent import MemoryStore


def _persist_failed_run(store: MemoryStore, agent: str, error_type: str, feedback: str) -> None:
    store.persist_session(
        results={agent: {"passed": False, "attempts": 1, "feedback": [feedback]}},
        judge_failures=[(agent, feedback)],
    )
    _ = store.db.execute(
        "UPDATE agent_runs SET error_type = ?, error = ? WHERE run_id = (SELECT MAX(id) FROM runs)",
        (error_type, feedback),
    )
    store.db.commit()


def test_recommend_seed_avoids_attempted_and_failed_history(tmp_path: Path) -> None:
    store = MemoryStore(str(tmp_path / "memory.db"))
    try:
        _persist_failed_run(store, "detection", "SchemaValidation", "bad schema")
        seed, reason = store.recommend_seed_for_agent("detection", attempted_seeds=[42], default_seed=42)

        assert seed == 43
        assert "avoiding 1 attempted and 1 failed seeds" in reason
    finally:
        store.close()


def test_prune_old_runs_deletes_redundant_failed_history(tmp_path: Path) -> None:
    store = MemoryStore(str(tmp_path / "memory.db"))
    try:
        _persist_failed_run(store, "auditing", "Unknown", "paper truncated")
        _persist_failed_run(store, "auditing", "Unknown", "paper truncated")
        _persist_failed_run(store, "auditing", "Unknown", "paper truncated")

        before_row = cast(sqlite3.Row | None, store.db.execute("SELECT COUNT(*) AS cnt FROM runs").fetchone())
        before = cast(int, before_row["cnt"] if before_row else 0)
        deleted = store.prune_old_runs(keep_recent=50)
        after_row = cast(sqlite3.Row | None, store.db.execute("SELECT COUNT(*) AS cnt FROM runs").fetchone())
        after = cast(int, after_row["cnt"] if after_row else 0)

        assert before == 3
        assert deleted == 2
        assert after == 1
    finally:
        store.close()
