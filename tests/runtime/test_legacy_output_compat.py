# pyright: reportAny=false, reportIndexIssue=false, reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportUnknownVariableType=false

from __future__ import annotations

from pathlib import Path

from _pytest.monkeypatch import MonkeyPatch

import pytest
try:
    from utils.context import PipelineContext
    import utils.context as context_module
    from utils.schemas import BaselineResults, MitigationResults  # type: ignore[attr-defined]
    _LEGACY_AVAILABLE = True
except (ImportError, AttributeError):
    _LEGACY_AVAILABLE = False

from tests.conftest import load_runtime_json, runtime_fixture_dir


@pytest.mark.skipif(not _LEGACY_AVAILABLE, reason="Legacy bias-audit schemas removed")
def test_runtime_fixtures_validate_existing_output_schemas(monkeypatch: MonkeyPatch) -> None:
    fixture_root = runtime_fixture_dir("auditing_revision_needed_session")
    outputs_dir = fixture_root / "outputs"

    baseline_payload = load_runtime_json("auditing_revision_needed_session", "outputs/baseline_results.json")
    mitigation_payload = load_runtime_json("auditing_revision_needed_session", "outputs/mitigation_results.json")

    assert BaselineResults.validate(baseline_payload) == []
    assert MitigationResults.validate(mitigation_payload) == []

    monkeypatch.setattr(context_module, "OUTPUT_DIR", str(outputs_dir))
    loaded = PipelineContext.load(seed=42)

    assert loaded.baseline is not None
    assert loaded.baseline.to_dict() == baseline_payload
    assert loaded.mitigation is not None
    assert loaded.mitigation.to_dict() == mitigation_payload
    assert loaded.paper_tex_path == str(outputs_dir / "paper" / "paper.tex")
    assert loaded.paper_pdf_path == str(outputs_dir / "paper" / "paper.pdf")


@pytest.mark.skipif(not _LEGACY_AVAILABLE, reason="Legacy bias-audit schemas removed")
def test_runtime_manifest_paths_resolve_to_current_outputs_tree() -> None:
    session = load_runtime_json("auditing_revision_needed_session")
    fixture_root = runtime_fixture_dir("auditing_revision_needed_session")
    manifest = session["artifact_manifest"]

    for relative_path in manifest["legacy_exports"].values():
        assert (fixture_root / Path(relative_path)).exists()
