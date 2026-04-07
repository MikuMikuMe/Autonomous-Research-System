"""
Formal I/O schemas for the Autonomous Research System.

Dataclasses defining data contracts between agents. All serialization is
backward-compatible with JSON files in outputs/.

No external dependencies — stdlib only (dataclasses, json).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from typing import Any


# ====================================================================
# Research claim schemas
# ====================================================================


@dataclass
class ClaimVerdict:
    """Result of cross-validating a research claim against literature."""
    claim: str
    verdict: str  # support | contradict | neutral
    confidence: float = 0.0
    supporting_papers: list[str] = field(default_factory=list)
    contradicting_papers: list[str] = field(default_factory=list)
    evidence_summary: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> ClaimVerdict:
        return cls(
            claim=d.get("claim", ""),
            verdict=d.get("verdict", "neutral"),
            confidence=d.get("confidence", 0.0),
            supporting_papers=d.get("supporting_papers", []),
            contradicting_papers=d.get("contradicting_papers", []),
            evidence_summary=d.get("evidence_summary", ""),
        )


@dataclass
class FlawRecord:
    """A detected flaw in the research."""
    description: str
    severity: str = "medium"  # critical | high | medium | low
    category: str = ""  # logical | statistical | methodological | data
    suggested_fix: str = ""
    source_claim: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> FlawRecord:
        return cls(
            description=d.get("description", ""),
            severity=d.get("severity", "medium"),
            category=d.get("category", ""),
            suggested_fix=d.get("suggested_fix", ""),
            source_claim=d.get("source_claim", ""),
        )


@dataclass
class ResearchIterationResult:
    """Summary of a single research loop iteration."""
    iteration: int
    verified_claims: int = 0
    contradicted_claims: int = 0
    papers_retrieved: int = 0
    flaws_detected: int = 0
    critical_flaws: int = 0
    verified_ratio: float = 0.0
    converged: bool = False
    evolved: bool = False
    duration_seconds: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> ResearchIterationResult:
        return cls(**{k: d[k] for k in cls.__dataclass_fields__ if k in d})


# ====================================================================
# Agent output schemas
# ====================================================================


@dataclass
class JudgeResult:
    passed: bool
    feedback: list[str] = field(default_factory=list)
    retry_hint: str | None = None
    actionable_feedback: str | None = None

    def to_dict(self) -> dict:
        d: dict[str, Any] = {"passed": self.passed, "feedback": self.feedback}
        if self.retry_hint is not None:
            d["retry_hint"] = self.retry_hint
        if self.actionable_feedback is not None:
            d["actionable_feedback"] = self.actionable_feedback
        return d

    @classmethod
    def from_dict(cls, d: dict) -> JudgeResult:
        return cls(
            passed=d["passed"],
            feedback=d.get("feedback", []),
            retry_hint=d.get("retry_hint"),
            actionable_feedback=d.get("actionable_feedback"),
        )


# ====================================================================
# Memory / self-evolution schemas
# ====================================================================


@dataclass
class AgentRunRecord:
    agent: str
    seed: int
    attempt: int
    passed: bool
    duration_seconds: float
    error: str | None = None
    error_type: str | None = None
    metrics_snapshot: dict | None = None
    judge_feedback: list[str] = field(default_factory=list)
    retry_hint: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> AgentRunRecord:
        return cls(**{k: d[k] for k in cls.__dataclass_fields__ if k in d})


@dataclass
class VerificationRecord:
    claim: str
    verified: bool | None
    evidence: str = ""
    error: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> VerificationRecord:
        return cls(
            claim=d.get("claim", ""),
            verified=d.get("verified"),
            evidence=d.get("evidence", ""),
            error=d.get("error"),
        )


@dataclass
class RunRecord:
    timestamp: str
    all_passed: bool
    total_duration_seconds: float
    mode: str = "goal"
    goal: str = ""
    iterations_completed: int = 0
    converged: bool = False
    verified_ratio: float = 0.0
    agents: list[AgentRunRecord] = field(default_factory=list)
    verifications: list[VerificationRecord] = field(default_factory=list)
    claim_verdicts: list[ClaimVerdict] = field(default_factory=list)
    flaws: list[FlawRecord] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "all_passed": self.all_passed,
            "total_duration_seconds": self.total_duration_seconds,
            "mode": self.mode,
            "goal": self.goal,
            "iterations_completed": self.iterations_completed,
            "converged": self.converged,
            "verified_ratio": self.verified_ratio,
            "agents": [a.to_dict() for a in self.agents],
            "verifications": [v.to_dict() for v in self.verifications],
            "claim_verdicts": [c.to_dict() for c in self.claim_verdicts],
            "flaws": [f.to_dict() for f in self.flaws],
        }

    @classmethod
    def from_dict(cls, d: dict) -> RunRecord:
        return cls(
            timestamp=d["timestamp"],
            all_passed=d.get("all_passed", False),
            total_duration_seconds=d.get("total_duration_seconds", 0.0),
            mode=d.get("mode", "goal"),
            goal=d.get("goal", ""),
            iterations_completed=d.get("iterations_completed", 0),
            converged=d.get("converged", False),
            verified_ratio=d.get("verified_ratio", 0.0),
            agents=[AgentRunRecord.from_dict(a) for a in d.get("agents", [])],
            verifications=[VerificationRecord.from_dict(v) for v in d.get("verifications", [])],
            claim_verdicts=[ClaimVerdict.from_dict(c) for c in d.get("claim_verdicts", [])],
            flaws=[FlawRecord.from_dict(f) for f in d.get("flaws", [])],
        )
