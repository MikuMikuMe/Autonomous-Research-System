"""
Cross-Session Memory — Long-term persistent memory that survives across pipeline invocations.

Extends MemoryStore with:
- User profiles (preferences, domain context, writing style)
- Cross-session knowledge base (findings that persist across runs)
- Domain expertise tracking
- Research history across sessions

Uses a separate DB file (cross_session_memory.db) in the user's home directory
so it persists even if the project directory is cleaned.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def _default_db_path() -> str:
    """Cross-session DB in user's home directory for persistence."""
    home = Path.home() / ".autonomous_research"
    home.mkdir(exist_ok=True)
    return str(home / "cross_session_memory.db")


_CROSS_SESSION_SCHEMA = """
CREATE TABLE IF NOT EXISTS user_profiles (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         TEXT    NOT NULL DEFAULT 'default',
    key             TEXT    NOT NULL,
    value           TEXT,
    updated_at      TEXT    NOT NULL,
    UNIQUE(user_id, key)
);

CREATE TABLE IF NOT EXISTS domain_expertise (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    domain          TEXT    NOT NULL,
    expertise_level REAL    DEFAULT 0.0,
    topics_explored TEXT,
    last_active     TEXT    NOT NULL,
    total_sessions  INTEGER DEFAULT 1,
    UNIQUE(domain)
);

CREATE TABLE IF NOT EXISTS research_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      TEXT    NOT NULL,
    timestamp       TEXT    NOT NULL,
    goal            TEXT,
    domain          TEXT,
    claims_count    INTEGER DEFAULT 0,
    converged       BOOLEAN DEFAULT 0,
    duration_s      REAL,
    summary         TEXT,
    key_findings    TEXT
);

CREATE TABLE IF NOT EXISTS persistent_knowledge (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    domain          TEXT,
    claim           TEXT    NOT NULL,
    confidence      REAL    DEFAULT 0.5,
    evidence_count  INTEGER DEFAULT 1,
    first_seen      TEXT    NOT NULL,
    last_confirmed  TEXT    NOT NULL,
    sources         TEXT,
    verdict         TEXT    DEFAULT 'neutral',
    UNIQUE(domain, claim)
);

CREATE TABLE IF NOT EXISTS technique_registry (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    domain          TEXT,
    technique_name  TEXT    NOT NULL,
    description     TEXT,
    category        TEXT,
    effectiveness   REAL    DEFAULT 0.5,
    use_count       INTEGER DEFAULT 0,
    discovered_via  TEXT,
    first_seen      TEXT    NOT NULL,
    UNIQUE(domain, technique_name)
);

CREATE TABLE IF NOT EXISTS learned_patterns (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern_type    TEXT    NOT NULL,
    description     TEXT    NOT NULL,
    context         TEXT,
    frequency       INTEGER DEFAULT 1,
    last_seen       TEXT    NOT NULL,
    UNIQUE(pattern_type, description)
);
"""


class CrossSessionMemory:
    """Long-term memory that persists across pipeline invocations."""

    def __init__(self, db_path: str | None = None, user_id: str = "default") -> None:
        self._db_path = db_path or _default_db_path()
        self._user_id = user_id
        db_dir = os.path.dirname(self._db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        self.db = sqlite3.connect(self._db_path)
        self.db.row_factory = sqlite3.Row
        self._ensure_tables()

    def _ensure_tables(self) -> None:
        self.db.executescript(_CROSS_SESSION_SCHEMA)
        self.db.commit()

    def close(self) -> None:
        self.db.close()

    # ── User Profiles ─────────────────────────────────────────────────────

    def set_preference(self, key: str, value: Any) -> None:
        """Set a user preference (persists across sessions)."""
        now = datetime.now().isoformat()
        val = json.dumps(value) if not isinstance(value, str) else value
        self.db.execute(
            """INSERT INTO user_profiles (user_id, key, value, updated_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(user_id, key) DO UPDATE SET value=?, updated_at=?""",
            (self._user_id, key, val, now, val, now),
        )
        self.db.commit()

    def get_preference(self, key: str, default: Any = None) -> Any:
        """Get a user preference."""
        row = self.db.execute(
            "SELECT value FROM user_profiles WHERE user_id = ? AND key = ?",
            (self._user_id, key),
        ).fetchone()
        if not row:
            return default
        try:
            return json.loads(row["value"])
        except (json.JSONDecodeError, TypeError):
            return row["value"]

    def get_all_preferences(self) -> dict[str, Any]:
        """Get all user preferences."""
        rows = self.db.execute(
            "SELECT key, value FROM user_profiles WHERE user_id = ?",
            (self._user_id,),
        ).fetchall()
        result = {}
        for r in rows:
            try:
                result[r["key"]] = json.loads(r["value"])
            except (json.JSONDecodeError, TypeError):
                result[r["key"]] = r["value"]
        return result

    # ── Domain Expertise ──────────────────────────────────────────────────

    def track_domain(self, domain: str, topics: list[str] | None = None) -> None:
        """Record activity in a research domain."""
        now = datetime.now().isoformat()
        existing = self.db.execute(
            "SELECT id, topics_explored, total_sessions, expertise_level FROM domain_expertise WHERE domain = ?",
            (domain,),
        ).fetchone()

        if existing:
            old_topics = json.loads(existing["topics_explored"] or "[]")
            all_topics = list(set(old_topics + (topics or [])))
            sessions = existing["total_sessions"] + 1
            # Expertise grows logarithmically with sessions
            import math
            expertise = min(1.0, 0.1 * math.log2(sessions + 1))
            self.db.execute(
                """UPDATE domain_expertise
                   SET topics_explored=?, last_active=?, total_sessions=?, expertise_level=?
                   WHERE id=?""",
                (json.dumps(all_topics), now, sessions, expertise, existing["id"]),
            )
        else:
            self.db.execute(
                """INSERT INTO domain_expertise (domain, topics_explored, last_active, expertise_level)
                   VALUES (?, ?, ?, 0.1)""",
                (domain, json.dumps(topics or []), now),
            )
        self.db.commit()

    def get_domain_expertise(self, domain: str | None = None) -> list[dict]:
        """Get expertise levels for all or a specific domain."""
        if domain:
            rows = self.db.execute(
                "SELECT * FROM domain_expertise WHERE domain = ?", (domain,)
            ).fetchall()
        else:
            rows = self.db.execute(
                "SELECT * FROM domain_expertise ORDER BY expertise_level DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    # ── Research History ──────────────────────────────────────────────────

    def log_session(
        self,
        session_id: str,
        goal: str,
        domain: str = "",
        claims_count: int = 0,
        converged: bool = False,
        duration_s: float = 0,
        summary: str = "",
        key_findings: list[str] | None = None,
    ) -> int:
        """Log a research session."""
        cur = self.db.execute(
            """INSERT INTO research_history
               (session_id, timestamp, goal, domain, claims_count, converged, duration_s, summary, key_findings)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                session_id,
                datetime.now().isoformat(),
                goal,
                domain,
                claims_count,
                converged,
                duration_s,
                summary,
                json.dumps(key_findings or []),
            ),
        )
        self.db.commit()

        if domain:
            self.track_domain(domain)

        return cur.lastrowid  # type: ignore[return-value]

    def get_research_history(self, domain: str = "", limit: int = 20) -> list[dict]:
        """Get recent research sessions, optionally filtered by domain."""
        if domain:
            rows = self.db.execute(
                "SELECT * FROM research_history WHERE domain = ? ORDER BY id DESC LIMIT ?",
                (domain, limit),
            ).fetchall()
        else:
            rows = self.db.execute(
                "SELECT * FROM research_history ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    # ── Persistent Knowledge ──────────────────────────────────────────────

    def store_knowledge(
        self,
        claim: str,
        domain: str = "",
        confidence: float = 0.5,
        sources: list[str] | None = None,
        verdict: str = "neutral",
    ) -> None:
        """Store or update a cross-session knowledge entry."""
        now = datetime.now().isoformat()
        existing = self.db.execute(
            "SELECT id, evidence_count, confidence, sources FROM persistent_knowledge WHERE domain = ? AND claim = ?",
            (domain, claim[:2000]),
        ).fetchone()

        if existing:
            old_sources = json.loads(existing["sources"] or "[]")
            all_sources = list(set(old_sources + (sources or [])))
            avg_confidence = (existing["confidence"] + confidence) / 2
            self.db.execute(
                """UPDATE persistent_knowledge
                   SET confidence=?, evidence_count=?, last_confirmed=?, sources=?, verdict=?
                   WHERE id=?""",
                (avg_confidence, existing["evidence_count"] + 1, now, json.dumps(all_sources), verdict, existing["id"]),
            )
        else:
            self.db.execute(
                """INSERT INTO persistent_knowledge (domain, claim, confidence, first_seen, last_confirmed, sources, verdict)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (domain, claim[:2000], confidence, now, now, json.dumps(sources or []), verdict),
            )
        self.db.commit()

    def get_knowledge(self, domain: str = "", query: str = "", limit: int = 20) -> list[dict]:
        """Retrieve persistent knowledge, optionally filtered."""
        if domain and query:
            rows = self.db.execute(
                "SELECT * FROM persistent_knowledge WHERE domain = ? AND claim LIKE ? ORDER BY confidence DESC LIMIT ?",
                (domain, f"%{query}%", limit),
            ).fetchall()
        elif domain:
            rows = self.db.execute(
                "SELECT * FROM persistent_knowledge WHERE domain = ? ORDER BY confidence DESC LIMIT ?",
                (domain, limit),
            ).fetchall()
        elif query:
            rows = self.db.execute(
                "SELECT * FROM persistent_knowledge WHERE claim LIKE ? ORDER BY confidence DESC LIMIT ?",
                (f"%{query}%", limit),
            ).fetchall()
        else:
            rows = self.db.execute(
                "SELECT * FROM persistent_knowledge ORDER BY confidence DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    # ── Technique Registry ────────────────────────────────────────────────

    def register_technique(
        self,
        technique_name: str,
        domain: str = "",
        description: str = "",
        category: str = "",
        effectiveness: float = 0.5,
        discovered_via: str = "research",
    ) -> None:
        """Register a discovered technique/method in long-term memory."""
        now = datetime.now().isoformat()
        existing = self.db.execute(
            "SELECT id, use_count, effectiveness FROM technique_registry WHERE domain = ? AND technique_name = ?",
            (domain, technique_name),
        ).fetchone()

        if existing:
            avg_eff = (existing["effectiveness"] + effectiveness) / 2
            self.db.execute(
                "UPDATE technique_registry SET use_count=?, effectiveness=? WHERE id=?",
                (existing["use_count"] + 1, avg_eff, existing["id"]),
            )
        else:
            self.db.execute(
                """INSERT INTO technique_registry
                   (domain, technique_name, description, category, effectiveness, discovered_via, first_seen)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (domain, technique_name, description, category, effectiveness, discovered_via, now),
            )
        self.db.commit()

    def get_techniques(self, domain: str = "", category: str = "", limit: int = 20) -> list[dict]:
        """Get discovered techniques, optionally filtered."""
        conditions = []
        params: list[Any] = []
        if domain:
            conditions.append("domain = ?")
            params.append(domain)
        if category:
            conditions.append("category = ?")
            params.append(category)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.append(limit)

        rows = self.db.execute(
            f"SELECT * FROM technique_registry {where} ORDER BY effectiveness DESC, use_count DESC LIMIT ?",
            params,
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Learned Patterns ──────────────────────────────────────────────────

    def learn_pattern(self, pattern_type: str, description: str, context: str = "") -> None:
        """Record a learned pattern (e.g., common pitfalls, effective strategies)."""
        now = datetime.now().isoformat()
        existing = self.db.execute(
            "SELECT id, frequency FROM learned_patterns WHERE pattern_type = ? AND description = ?",
            (pattern_type, description[:2000]),
        ).fetchone()

        if existing:
            self.db.execute(
                "UPDATE learned_patterns SET frequency=?, last_seen=?, context=? WHERE id=?",
                (existing["frequency"] + 1, now, context, existing["id"]),
            )
        else:
            self.db.execute(
                "INSERT INTO learned_patterns (pattern_type, description, context, last_seen) VALUES (?, ?, ?, ?)",
                (pattern_type, description[:2000], context, now),
            )
        self.db.commit()

    def get_patterns(self, pattern_type: str = "", limit: int = 20) -> list[dict]:
        """Get learned patterns."""
        if pattern_type:
            rows = self.db.execute(
                "SELECT * FROM learned_patterns WHERE pattern_type = ? ORDER BY frequency DESC LIMIT ?",
                (pattern_type, limit),
            ).fetchall()
        else:
            rows = self.db.execute(
                "SELECT * FROM learned_patterns ORDER BY frequency DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    # ── Cross-Session Summary ─────────────────────────────────────────────

    def cross_session_summary(self) -> dict:
        """Full cross-session state summary for LLM context injection."""
        total_sessions = self.db.execute("SELECT COUNT(*) as cnt FROM research_history").fetchone()
        total_knowledge = self.db.execute("SELECT COUNT(*) as cnt FROM persistent_knowledge").fetchone()
        total_techniques = self.db.execute("SELECT COUNT(*) as cnt FROM technique_registry").fetchone()

        return {
            "total_sessions": total_sessions["cnt"] if total_sessions else 0,
            "total_knowledge_entries": total_knowledge["cnt"] if total_knowledge else 0,
            "total_techniques": total_techniques["cnt"] if total_techniques else 0,
            "domains": self.get_domain_expertise(),
            "preferences": self.get_all_preferences(),
            "recent_sessions": self.get_research_history(limit=5),
            "top_techniques": self.get_techniques(limit=10),
            "common_patterns": self.get_patterns(limit=10),
        }
