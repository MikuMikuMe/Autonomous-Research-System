# pyright: reportAny=false, reportUnknownMemberType=false, reportUnknownVariableType=false

from __future__ import annotations

from utils.events import EventType, PipelineEvent

from tests.conftest import load_runtime_json


def test_detection_session_events_follow_queue_contract() -> None:
    session = load_runtime_json("passing_detection_session")

    expected_events = [
        PipelineEvent(type=EventType.AGENT_STARTED, agent="detection").to_queue_dict(),
        PipelineEvent(type=EventType.AGENT_LOG, agent="detection", line="Loading dataset split.").to_queue_dict(),
        PipelineEvent(type=EventType.AGENT_PROGRESS, agent="detection", progress=0.25, label="load_dataset").to_queue_dict(),
        PipelineEvent(type=EventType.AGENT_PROGRESS, agent="detection", progress=0.75, label="train_models").to_queue_dict(),
        PipelineEvent(type=EventType.AGENT_FINISHED, agent="detection", returncode=0).to_queue_dict(),
        PipelineEvent(
            type=EventType.JUDGE_RESULT,
            agent="detection",
            passed=True,
            feedback=["Detection OK: 2 models, 2 with violations."],
            retry_hint=None,
            attempt=1,
        ).to_queue_dict(),
        PipelineEvent(type=EventType.OUTPUTS_UPDATED, agent="detection").to_queue_dict(),
    ]

    assert session["events"] == expected_events


def test_revision_session_events_hold_order_until_pipeline_stop() -> None:
    session = load_runtime_json("auditing_revision_needed_session")

    expected_events = [
        PipelineEvent(type=EventType.AGENT_STARTED, agent="auditing").to_queue_dict(),
        PipelineEvent(type=EventType.AGENT_LOG, agent="auditing", line="Drafting paper revision from latest outputs.").to_queue_dict(),
        PipelineEvent(type=EventType.AGENT_FINISHED, agent="auditing", returncode=0).to_queue_dict(),
        PipelineEvent(
            type=EventType.JUDGE_RESULT,
            agent="auditing",
            passed=False,
            feedback=[
                "Claims overstate fairness compliance.",
                "Discussion section must reflect threshold-adjustment dependency.",
            ],
            retry_hint="revise_claims",
            attempt=1,
        ).to_queue_dict(),
        PipelineEvent(type=EventType.OUTPUTS_UPDATED, agent="auditing").to_queue_dict(),
        PipelineEvent(
            type=EventType.PIPELINE_FINISHED,
            all_passed=False,
            results={"auditing": "revision_needed"},
        ).to_queue_dict(),
    ]

    assert session["events"] == expected_events
