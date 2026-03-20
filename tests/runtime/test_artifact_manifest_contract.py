# pyright: reportAny=false, reportArgumentType=false, reportIndexIssue=false, reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownVariableType=false

from __future__ import annotations

from pathlib import Path

from tests.conftest import runtime_fixture_dir, load_runtime_json


EXPECTED_EXPORTS = {
    "baseline_results_json": "outputs/baseline_results.json",
    "mitigation_results_json": "outputs/mitigation_results.json",
    "structure_review_json": "outputs/structure_review.json",
    "paper_draft_md": "outputs/paper_draft.md",
    "paper_tex": "outputs/paper/paper.tex",
    "paper_pdf": "outputs/paper/paper.pdf",
}

EXPECTED_INDEX_KEYS = {
    "baseline_results",
    "mitigation_results",
    "structure_review",
    "paper_draft",
    "paper_tex",
    "paper_pdf",
}


def test_artifact_manifest_matches_export_contract() -> None:
    session = load_runtime_json("auditing_revision_needed_session")
    fixture_root = runtime_fixture_dir("auditing_revision_needed_session")
    manifest = session["artifact_manifest"]

    assert set(manifest) == {
        "schema_version",
        "session_id",
        "generated_at",
        "legacy_exports",
        "exported_paper_artifacts",
        "artifact_index",
    }
    assert manifest["schema_version"] == "runtime_artifact_manifest.v1"
    assert manifest["legacy_exports"] == EXPECTED_EXPORTS
    assert manifest["exported_paper_artifacts"] == {
        "draft_markdown": "outputs/paper_draft.md",
        "latex_source": "outputs/paper/paper.tex",
        "compiled_pdf": "outputs/paper/paper.pdf",
        "structure_review": "outputs/structure_review.json",
    }

    artifact_index = manifest["artifact_index"]
    assert set(artifact_index) == EXPECTED_INDEX_KEYS

    for name, entry in artifact_index.items():
        assert set(entry) == {"path", "producer", "kind", "media_type", "required", "legacy_output"}
        assert entry["legacy_output"] is True
        assert entry["required"] is True
        assert entry["path"].startswith("outputs/")
        assert (fixture_root / Path(entry["path"])).exists(), name


def test_paper_exports_stay_pointer_compatible_for_future_runtime() -> None:
    session = load_runtime_json("auditing_revision_needed_session")
    exports = session["artifact_manifest"]["exported_paper_artifacts"]

    assert exports["draft_markdown"] == EXPECTED_EXPORTS["paper_draft_md"]
    assert exports["latex_source"] == EXPECTED_EXPORTS["paper_tex"]
    assert exports["compiled_pdf"] == EXPECTED_EXPORTS["paper_pdf"]
    assert exports["structure_review"] == EXPECTED_EXPORTS["structure_review_json"]
