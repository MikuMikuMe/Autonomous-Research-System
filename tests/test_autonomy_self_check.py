# pyright: reportAny=false, reportUnknownMemberType=false, reportUnknownVariableType=false

"""Tests that validate the system's autonomous agentic capabilities.

Covers the DISCOVER → PLAN → ACT → OBSERVE → REFLECT workflow:
- Self-check agent runs and produces structured reports
- Knowledge compaction removes redundant entries
- Continuous runner orchestrates iterations with compaction
- Memory agent handles the full lifecycle (persist → query → compact → prune)
"""

from __future__ import annotations

import json
from unittest.mock import patch, MagicMock

from agents.self_check_agent import run_self_check, CheckResult, SelfCheckReport
from agents.memory_agent import MemoryStore
from utils.schemas import RunRecord, AgentRunRecord


# ====================================================================
# DISCOVER: Self-check agent
# ====================================================================


def test_self_check_produces_structured_report() -> None:
    """Self-check produces a report with all five agentic phases."""
    report = run_self_check()

    assert isinstance(report, SelfCheckReport)
    assert report.total_checks > 0
    assert report.passed + report.failed == report.total_checks
    assert set(report.phases.keys()) == {"DISCOVER", "PLAN", "ACT", "OBSERVE", "REFLECT"}

    for phase, checks in report.phases.items():
        assert len(checks) > 0, f"Phase {phase} has no checks"
        for check in checks:
            assert isinstance(check, CheckResult)
            assert check.phase == phase
            assert check.name
            assert check.message


def test_self_check_discover_phase_verifies_imports() -> None:
    """DISCOVER phase checks that core agent modules are importable."""
    report = run_self_check()
    discover_checks = report.phases.get("DISCOVER", [])

    import_checks = [c for c in discover_checks if c.name.startswith("import:")]
    assert len(import_checks) >= 5, "Should check at least 5 core agent imports"

    # At minimum, these should be importable
    expected_modules = {"agents.judge_agent", "agents.memory_agent", "agents.verification_agent"}
    import_names = {c.name.replace("import:", "") for c in import_checks if c.passed}
    assert expected_modules.issubset(import_names)


def test_self_check_plan_phase_verifies_ordering() -> None:
    """PLAN phase checks agent ordering and retry config."""
    report = run_self_check()
    plan_checks = report.phases.get("PLAN", [])

    ordering_check = next((c for c in plan_checks if "ordering" in c.name), None)
    assert ordering_check is not None
    assert ordering_check.passed, ordering_check.message

    retry_check = next((c for c in plan_checks if "retry" in c.name), None)
    assert retry_check is not None
    assert retry_check.passed, retry_check.message


def test_self_check_act_phase_verifies_runtime() -> None:
    """ACT phase checks that the runtime can be instantiated."""
    report = run_self_check()
    act_checks = report.phases.get("ACT", [])

    runtime_check = next((c for c in act_checks if "runtime" in c.name), None)
    assert runtime_check is not None
    assert runtime_check.passed, runtime_check.message


def test_self_check_observe_phase_verifies_events() -> None:
    """OBSERVE phase checks EventBus delivery and schema validation."""
    report = run_self_check()
    observe_checks = report.phases.get("OBSERVE", [])

    event_check = next((c for c in observe_checks if "event_bus" in c.name), None)
    assert event_check is not None
    assert event_check.passed, event_check.message

    schema_check = next((c for c in observe_checks if "schema" in c.name), None)
    assert schema_check is not None
    assert schema_check.passed, schema_check.message


def test_self_check_reflect_phase_verifies_memory() -> None:
    """REFLECT phase checks memory persistence, compaction, and seed recommendation."""
    report = run_self_check()
    reflect_checks = report.phases.get("REFLECT", [])

    memory_check = next((c for c in reflect_checks if "memory_store" in c.name), None)
    assert memory_check is not None
    assert memory_check.passed, memory_check.message

    compact_check = next((c for c in reflect_checks if "compaction" in c.name), None)
    assert compact_check is not None
    assert compact_check.passed, compact_check.message

    seed_check = next((c for c in reflect_checks if "seed" in c.name), None)
    assert seed_check is not None
    assert seed_check.passed, seed_check.message


def test_self_check_report_serializes_to_json() -> None:
    """Self-check report can be serialized to JSON."""
    report = run_self_check()
    d = report.to_dict()
    serialized = json.dumps(d, default=str)
    assert len(serialized) > 100
    parsed = json.loads(serialized)
    assert parsed["total_checks"] == report.total_checks
    assert parsed["is_autonomous"] == report.is_autonomous


# ====================================================================
# REFLECT: Knowledge compaction
# ====================================================================


def test_compact_knowledge_deduplicates_insights() -> None:
    """compact_knowledge removes duplicate idea insights within the same domain."""
    store = MemoryStore(db_path=":memory:")

    # Insert duplicate insights
    for i in range(4):
        store.db.execute(
            "INSERT INTO idea_insights (session_id, domain, insight, insight_type, timestamp) "
            "VALUES (?, ?, ?, ?, ?)",
            (f"sess_{i}", "fairness", "Check for class imbalance before training",
             "pitfall", f"2026-01-0{i + 1}T00:00:00Z"),
        )
    # Insert a unique insight
    store.db.execute(
        "INSERT INTO idea_insights (session_id, domain, insight, insight_type, timestamp) "
        "VALUES (?, ?, ?, ?, ?)",
        ("sess_unique", "fairness", "Verify EU AI Act thresholds", "pitfall", "2026-01-05T00:00:00Z"),
    )
    store.db.commit()

    before = store.db.execute("SELECT COUNT(*) as cnt FROM idea_insights").fetchone()["cnt"]
    assert before == 5

    removed = store.compact_knowledge()
    after = store.db.execute("SELECT COUNT(*) as cnt FROM idea_insights").fetchone()["cnt"]

    assert removed["idea_insights"] == 3  # 4 duplicates → keep 1, remove 3
    assert after == 2  # 1 kept duplicate + 1 unique
    store.close()


def test_compact_knowledge_deduplicates_verifications() -> None:
    """compact_knowledge keeps only the most recent verification per claim."""
    store = MemoryStore(db_path=":memory:")

    # Create a run for the verifications to reference
    store.db.execute(
        "INSERT INTO runs (timestamp, seed, all_passed, duration_s) VALUES (?, ?, ?, ?)",
        ("2026-01-01T00:00:00Z", 42, 1, 10.0),
    )
    run_id = store.db.execute("SELECT last_insert_rowid()").fetchone()[0]

    # Insert duplicate verifications for the same claim
    for i in range(3):
        store.db.execute(
            "INSERT INTO verifications (run_id, claim, verified, evidence, error) "
            "VALUES (?, ?, ?, ?, ?)",
            (run_id, "Accuracy loss is minimal", i % 2 == 0, f"evidence_{i}", None),
        )
    store.db.commit()

    removed = store.compact_knowledge()
    after = store.db.execute("SELECT COUNT(*) as cnt FROM verifications").fetchone()["cnt"]

    assert removed["verifications"] == 2  # 3 → keep 1
    assert after == 1
    store.close()


def test_compact_knowledge_collapses_redundant_agent_feedback() -> None:
    """compact_knowledge collapses >2 identical failed agent_runs to keep 2."""
    store = MemoryStore(db_path=":memory:")

    # Create runs
    for i in range(5):
        store.db.execute(
            "INSERT INTO runs (timestamp, seed, all_passed, duration_s) VALUES (?, ?, ?, ?)",
            (f"2026-01-0{i + 1}T00:00:00Z", 42, 0, 10.0),
        )
        run_id = store.db.execute("SELECT last_insert_rowid()").fetchone()[0]
        store.db.execute(
            "INSERT INTO agent_runs (run_id, agent, seed, attempt, passed, duration_s, "
            "error, error_type, judge_feedback) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (run_id, "auditing", 42, 1, False, 5.0,
             "timeout", "GeminiTimeout", '["timeout occurred"]'),
        )
    store.db.commit()

    before = store.db.execute("SELECT COUNT(*) as cnt FROM agent_runs").fetchone()["cnt"]
    assert before == 5

    removed = store.compact_knowledge()
    after = store.db.execute("SELECT COUNT(*) as cnt FROM agent_runs").fetchone()["cnt"]

    assert removed["agent_runs"] == 3  # 5 → keep 2
    assert after == 2
    store.close()


def test_compact_knowledge_handles_empty_database() -> None:
    """compact_knowledge works on an empty database without errors."""
    store = MemoryStore(db_path=":memory:")
    removed = store.compact_knowledge()

    assert removed["idea_insights"] == 0
    assert removed["verifications"] == 0
    assert removed["agent_runs"] == 0
    store.close()


# ====================================================================
# Full lifecycle: persist → compact → query
# ====================================================================


def test_memory_lifecycle_persist_compact_query() -> None:
    """Full lifecycle: persist runs, compact, verify data integrity."""
    store = MemoryStore(db_path=":memory:")

    # Persist 10 runs with the same failure pattern
    for i in range(10):
        record = RunRecord(
            timestamp=f"2026-01-{i + 1:02d}T00:00:00Z",
            seed=42,
            all_passed=False,
            total_duration_seconds=10.0,
            agents=[AgentRunRecord(
                agent="detection", seed=42, attempt=1,
                passed=False, duration_seconds=5.0,
                error="timeout", error_type="GeminiTimeout",
                judge_feedback=["timeout occurred"],
            )],
        )
        store.persist_run(record)

    # Persist 2 successful runs
    for i in range(2):
        record = RunRecord(
            timestamp=f"2026-02-{i + 1:02d}T00:00:00Z",
            seed=43 + i,
            all_passed=True,
            total_duration_seconds=60.0,
            agents=[AgentRunRecord(
                agent="detection", seed=43 + i, attempt=1,
                passed=True, duration_seconds=30.0,
            )],
        )
        store.persist_run(record)

    # Verify data before compaction
    total_runs = store.db.execute("SELECT COUNT(*) as cnt FROM runs").fetchone()["cnt"]
    total_agent_runs = store.db.execute("SELECT COUNT(*) as cnt FROM agent_runs").fetchone()["cnt"]
    assert total_runs == 12
    assert total_agent_runs == 12

    # Compact
    compacted = store.compact_knowledge()
    pruned = store.prune_old_runs(keep_recent=5)

    # Verify successful runs are preserved
    remaining_runs = store.db.execute("SELECT COUNT(*) as cnt FROM runs").fetchone()["cnt"]
    assert remaining_runs <= 6  # at most 5 recent + protected

    # Journey summary should still work
    summary = store.journey_summary()
    assert summary["total_runs"] > 0
    assert "detection" in summary["agents"]

    # Seed recommendation should prefer successful seed
    seed, reason = store.recommend_seed_for_agent("detection", [42], default_seed=42)
    assert seed != 42 or "best" in reason.lower() or "success" in reason.lower()

    store.close()


# ====================================================================
# Continuous runner (mocked pipeline)
# ====================================================================


def test_continuous_runner_self_check_mode() -> None:
    """Continuous runner --self-check runs diagnostics without pipeline."""
    from orchestration.continuous_runner import main

    exit_code = main(["--self-check", "--quiet"])
    assert exit_code == 0  # Should pass since all modules are importable


def test_continuous_runner_compact_only_mode() -> None:
    """Continuous runner --compact-only runs compaction without pipeline."""
    from orchestration.continuous_runner import main

    exit_code = main(["--compact-only", "--quiet"])
    assert exit_code == 0


def test_continuous_runner_zero_iterations() -> None:
    """Continuous runner with 0 iterations runs self-check + compaction only."""
    from orchestration.continuous_runner import run_continuous

    report = run_continuous(iterations=0, quiet=True)
    assert report["self_check_passed"] is True
    assert report["iterations_completed"] == 0
    assert len(report["compaction_results"]) >= 1
