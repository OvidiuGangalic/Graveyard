from __future__ import annotations

import importlib

from graveyard import config


def test_limits_are_off_by_default(monkeypatch):
    for name in [
        "MAX_REPO_SIZE_KB",
        "CLONE_TIMEOUT_S",
        "MAX_CLONE_DISK_MB",
        "MAX_SOURCE_FILES",
        "MAX_FILE_BYTES",
        "MAX_ITEMS",
        "ANALYSIS_TIMEOUT_S",
        "RATE_LIMIT_COUNT",
    ]:
        monkeypatch.delenv(f"GRAVEYARD_{name}", raising=False)
    reloaded = importlib.reload(config)
    assert reloaded.MAX_SOURCE_FILES is None
    assert reloaded.MAX_REPO_SIZE_KB is None
    assert reloaded.ANALYSIS_TIMEOUT_S is None
    assert reloaded.RATE_LIMIT_COUNT is None
    assert reloaded.CLONE_DEPTH == 500


def test_limit_can_be_switched_on_by_env(monkeypatch):
    monkeypatch.setenv("GRAVEYARD_MAX_SOURCE_FILES", "5000")
    monkeypatch.setenv("GRAVEYARD_CLONE_TIMEOUT_S", "not-a-number")
    reloaded = importlib.reload(config)
    assert reloaded.MAX_SOURCE_FILES == 5000
    assert reloaded.CLONE_TIMEOUT_S is None
    monkeypatch.delenv("GRAVEYARD_MAX_SOURCE_FILES")
    monkeypatch.delenv("GRAVEYARD_CLONE_TIMEOUT_S")
    importlib.reload(config)


def test_data_dir_follows_env(monkeypatch, tmp_path):
    monkeypatch.setenv("GRAVEYARD_DATA_DIR", str(tmp_path))
    assert config.data_dir() == tmp_path
