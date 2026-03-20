# pyright: reportAny=false, reportIndexIssue=false, reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownVariableType=false

from __future__ import annotations

from utils.schemas import AgentRunRecord, JudgeResult

from tests.conftest import load_runtime_json


EXPECTED_SESSION_KEYS = {
    "schema_version",
    "session_id",
    "pipeline_seed",
    "status",
    "current_stage",
    "started_at",
    "updated_at",
    "retry_metadata",
    "judge_results",
    "agent_runs",
    "artifact_manifest",
    "events",
}


def test_passing_detection_session_contract_is_stable() -> None:
    session = load_runtime_json("passing_detection_session")

    assert set(session) == EXPECTED_SESSION_KEYS
    assert session["schema_version"] == "runtime_session_contract.v1"
    assert session["session_id"] == "sess_detection_pass_20260310T120000Z"
    assert session["pipeline_seed"] == 42
    assert session["status"] == "running"
    assert session["current_stage"] == "mitigation"
    assert session["artifact_manifest"]["session_id"] == session["session_id"]

    assert session["retry_metadata"] == {
        "agent": "detection",
        "attempt": 1,
        "max_attempts": 3,
        "seed": 42,
        "retry_hint": None,
        "next_retry_seed": None,
        "status": "passed",
    }

    judge_result = JudgeResult.from_dict(session["judge_results"]["detection"])
    assert judge_result.to_dict() == session["judge_results"]["detection"]

    agent_run = AgentRunRecord.from_dict(session["agent_runs"][0])
    assert agent_run.to_dict() == session["agent_runs"][0]


def test_revision_needed_session_contract_captures_retry_state() -> None:
    session = load_runtime_json("auditing_revision_needed_session")

    assert set(session) == EXPECTED_SESSION_KEYS
    assert session["schema_version"] == "runtime_session_contract.v1"
    assert session["session_id"] == "sess_auditing_revision_needed_20260310T123000Z"
    assert session["pipeline_seed"] == 42
    assert session["status"] == "needs_revision"
    assert session["current_stage"] == "auditing"

    assert session["retry_metadata"] == {
        "agent": "auditing",
        "attempt": 1,
        "max_attempts": 3,
        "seed": 42,
        "retry_hint": "revise_claims",
        "next_retry_seed": None,
        "status": "awaiting_revision",
    }

    judge_result = JudgeResult.from_dict(session["judge_results"]["auditing"])
    assert judge_result.to_dict() == session["judge_results"]["auditing"]
    assert judge_result.actionable_feedback == "Align the discussion with the structure review findings."

    agent_run = AgentRunRecord.from_dict(session["agent_runs"][0])
    assert agent_run.retry_hint == "revise_claims"
    assert agent_run.judge_feedback == [
        "Claims overstate fairness compliance.",
        "Discussion section must reflect threshold-adjustment dependency.",
    ]
