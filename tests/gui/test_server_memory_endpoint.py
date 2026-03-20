from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient
from _pytest.monkeypatch import MonkeyPatch

from agents import memory_agent
from gui import server


class _MemoryStoreStub:
    def __init__(self) -> None:
        self.closed: bool = False

    def journey_summary(self) -> dict[str, Any]:
        return {"total_runs": 2, "agents": {"detection": {"success_rate": 1.0}}}

    def close(self) -> None:
        self.closed = True


def test_memory_journey_endpoint_returns_summary(monkeypatch: MonkeyPatch) -> None:
    store = _MemoryStoreStub()

    monkeypatch.setattr(memory_agent, "MemoryStore", lambda: store)

    client = TestClient(server.app)
    response = client.get("/api/memory/journey")

    assert response.status_code == 200
    assert response.json() == {"total_runs": 2, "agents": {"detection": {"success_rate": 1.0}}}
    assert store.closed is True
