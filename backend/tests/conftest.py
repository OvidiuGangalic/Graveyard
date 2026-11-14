from __future__ import annotations

import os

import pytest
from hypothesis import settings

settings.register_profile("dev", max_examples=100, deadline=None)
settings.register_profile("ci", max_examples=300, deadline=None, derandomize=True)
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "dev"))


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if os.environ.get("GRAVEYARD_NETWORK") == "1":
        return
    skip = pytest.mark.skip(reason="network test; set GRAVEYARD_NETWORK=1 to run")
    for item in items:
        if "network" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(autouse=True)
def _isolated_data_dir(tmp_path, monkeypatch):
    """Every test gets its own GRAVEYARD_DATA_DIR."""
    monkeypatch.setenv("GRAVEYARD_DATA_DIR", str(tmp_path / "data"))
