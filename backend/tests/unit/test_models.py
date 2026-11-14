from __future__ import annotations

from datetime import UTC, datetime

from graveyard.models import (
    BLIND_FLAGS,
    CAUTION_FLAGS,
    REVIVE_FLAGS,
    Analysis,
    DeadItem,
    Flag,
    LastCommit,
    RepoRef,
)


def test_repo_ref_urls():
    ref = RepoRef("example-org", "example-repo")
    assert ref.canonical_url == "https://github.com/example-org/example-repo"
    assert ref.clone_url == "https://github.com/example-org/example-repo.git"
    assert ref.repo_name == "example-org/example-repo"


def test_flag_groups_are_disjoint():
    assert not (REVIVE_FLAGS & BLIND_FLAGS)
    assert not (REVIVE_FLAGS & CAUTION_FLAGS)
    assert not (BLIND_FLAGS & CAUTION_FLAGS)
    assert Flag.ARITY_MISMATCH in CAUTION_FLAGS


def test_dead_item_round_trips_through_json():
    item = DeadItem(
        id="3f9a1c2e7b04",
        name="export_legacy_csv",
        kind="function",
        language="python",
        file_path="inventory/reports.py",
        start_line=11,
        end_line=16,
        last_commit=LastCommit(
            hash="1" * 40, date=datetime(2024, 12, 1, 9, tzinfo=UTC), author="Morticia Graves"
        ),
        age_days=730,
        confidence="high",
        verdict="bury",
        verdict_reason="No references anywhere in this repo.",
        code_snippet="def export_legacy_csv(rows, path):\n    ...",
    )
    assert DeadItem.model_validate_json(item.model_dump_json()) == item


def test_analysis_defaults_match_the_api_shape():
    analysis = Analysis(
        id="k3Jx9aQ2mLp1",
        repo_url="https://github.com/o/r",
        repo_name="o/r",
        branch="main",
        commit_analysed="9" * 40,
        created_at=datetime(2026, 12, 1, tzinfo=UTC),
    )
    data = analysis.model_dump(mode="json")
    assert data["status"] == "queued"
    assert data["items_by_language"] == {"python": 0, "typescript": 0}
    assert data["items_by_verdict"] == {"bury": 0, "revive": 0, "unsure": 0}
    assert data["progress"] == {"phase": "queued", "files_discovered": 0, "queue_position": 0}
    assert data["warnings"] == []
    assert Analysis.model_validate_json(analysis.model_dump_json()) == analysis
