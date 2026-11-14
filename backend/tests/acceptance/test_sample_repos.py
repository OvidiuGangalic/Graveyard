"""The accuracy gate (spec 05, Requirement 6): the full pipeline against the sample repos."""

from __future__ import annotations

import json
import random
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from graveyard import config
from graveyard.ingestion.samples import sample_snapshot
from graveyard.models import DeadItem
from graveyard.pipeline import PipelineResult, run

pytestmark = pytest.mark.acceptance

Key = tuple[str, str, str, str]  # (name, kind, language, file_path)


def _expected(dirname: str) -> dict:
    return json.loads((config.samples_dir() / dirname / "expected.json").read_text("utf-8"))


def _key(d: dict | DeadItem) -> Key:
    if isinstance(d, DeadItem):
        return (d.name, d.kind, d.language, d.file_path)
    return (d["name"], d["kind"], d["language"], d["file_path"])


def _analyse(name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> PipelineResult:
    monkeypatch.setenv("GRAVEYARD_DATA_DIR", str(tmp_path / "data"))
    return run(sample_snapshot(name), datetime.now(UTC))  # type: ignore[arg-type]


def _problems(expected: list[dict], items: list[DeadItem], language: str) -> list[str]:
    """Table rows (item | expected | actual | reason) for every mismatch; empty when it passes."""
    want = {_key(e): e for e in expected if e["language"] == language}
    got = {_key(i): i for i in items if i.language == language}
    rows = []
    for key, e in want.items():
        i = got.get(key)
        exp = f"{e['verdict']}/{e['confidence']}"
        where = f"{key[0]} ({key[3]})"
        if i is None:
            rows.append(f"{where} | {exp} | MISSING | not reported")
        elif (i.verdict, i.confidence) != (e["verdict"], e["confidence"]):
            rows.append(f"{where} | {exp} | {i.verdict}/{i.confidence} | {i.verdict_reason}")
    for key, i in got.items():
        if key not in want:
            actual = f"{i.verdict}/{i.confidence}"
            rows.append(f"{key[0]} ({key[3]}) | (none) | {actual} | UNEXPECTED: {i.verdict_reason}")
    return rows


def _assert_clean(rows: list[str]) -> None:
    assert not rows, "\nitem | expected | actual | reason\n" + "\n".join(rows)


@pytest.fixture
def haunted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> PipelineResult:
    return _analyse("haunted", tmp_path, monkeypatch)


def test_haunted_python_matches_expected(haunted: PipelineResult) -> None:
    _assert_clean(_problems(_expected("haunted-repo")["items"], list(haunted.items), "python"))


@pytest.mark.xfail(strict=True, reason="TypeScript analyser not wired in yet")
def test_haunted_typescript_matches_expected(haunted: PipelineResult) -> None:
    _assert_clean(_problems(_expected("haunted-repo")["items"], list(haunted.items), "typescript"))


def test_living_matches_expected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    items = list(_analyse("living", tmp_path, monkeypatch).items)
    spec = _expected("living-repo")
    forbidden = spec["forbidden"]
    rows = [
        f"{i.name} ({i.file_path}) | none of {forbidden} | {i.verdict}/{i.confidence} | "
        f"{i.verdict_reason}"
        for i in items
        if i.verdict in forbidden["verdicts"] or i.confidence in forbidden["confidences"]
    ]
    rows += _problems(spec["items"], items, "python")
    rows += _problems(spec["items"], items, "typescript")  # the living repo has no TS items
    _assert_clean(rows)


def test_pipeline_is_deterministic_and_order_independent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P4 as an example on the haunted sample; a full Hypothesis property would be too slow."""
    monkeypatch.setenv("GRAVEYARD_DATA_DIR", str(tmp_path / "data"))
    snapshot = sample_snapshot("haunted")
    created_at = datetime.now(UTC)
    first = run(snapshot, created_at)
    files = list(snapshot.source_files)
    random.Random(4).shuffle(files)
    assert run(replace(snapshot, source_files=tuple(files)), created_at) == first
    assert run(snapshot, created_at) == first
