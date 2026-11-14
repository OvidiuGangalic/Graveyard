"""Every limit and threshold, in one place.

Owner decision (14 Nov 2026): size, file-count, time, item and rate limits are off by
default. A value of ``None`` disables the check. Each can be switched on with an
environment variable named ``GRAVEYARD_<CONSTANT>``.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def _int(name: str, default: int) -> int:
    raw = os.environ.get(f"GRAVEYARD_{name}", "").strip()
    try:
        return int(raw) if raw else default
    except ValueError:
        return default


def _optional_int(name: str) -> int | None:
    raw = os.environ.get(f"GRAVEYARD_{name}", "").strip()
    try:
        value = int(raw) if raw else None
    except ValueError:
        return None
    return value if value is not None and value > 0 else None


# --- ingestion (spec 01) ---
MAX_URL_LENGTH = 300
LS_REMOTE_TIMEOUT_S = 10
GITHUB_API_TIMEOUT_S = 5
CLONE_DEPTH = _int("CLONE_DEPTH", 500)
MAX_TEXT_FILE_BYTES = 1_048_576

MAX_REPO_SIZE_KB: int | None = _optional_int("MAX_REPO_SIZE_KB")
CLONE_TIMEOUT_S: int | None = _optional_int("CLONE_TIMEOUT_S")
MAX_CLONE_DISK_MB: int | None = _optional_int("MAX_CLONE_DISK_MB")
MAX_SOURCE_FILES: int | None = _optional_int("MAX_SOURCE_FILES")
MAX_FILE_BYTES: int | None = _optional_int("MAX_FILE_BYTES")

# --- analysers (specs 02, 03) ---
SNIPPET_MAX_LINES = 200
MAX_CALLERS = 20
MAX_OCCURRENCES_PER_NAME = 50
SHORT_NAME_LENGTH = 3  # names this short are not searched in text-reference files
REEXPORT_DEPTH = 5

# --- git archaeology (spec 04) ---
MAX_BLAME_ITEMS = 300
GIT_CMD_TIMEOUT_S = 10

# --- verdicts and pipeline (spec 05) ---
OLD_AGE_DAYS = 180
MAX_ITEMS: int | None = _optional_int("MAX_ITEMS")
ANALYSIS_TIMEOUT_S: int | None = _optional_int("ANALYSIS_TIMEOUT_S")

# --- API (spec 07) ---
MAX_CONCURRENT_JOBS = 1
MAX_QUEUE = 4
RATE_LIMIT_COUNT: int | None = _optional_int("RATE_LIMIT_COUNT")
RATE_LIMIT_WINDOW_S = 600
TTL_S = 86_400
MAX_STORED = 200
MAX_BODY_BYTES = 2_048

SAMPLE_WARNING = "Sample repo: commit history is scripted, so ages are illustrative"


def data_dir() -> Path:
    """Clone and cache directory. Read at call time so tests can redirect it."""
    raw = os.environ.get("GRAVEYARD_DATA_DIR", "").strip()
    return Path(raw) if raw else Path(tempfile.gettempdir()) / "graveyard"


def samples_dir() -> Path:
    """Where the sample repos' sources live (repo root /samples by default)."""
    raw = os.environ.get("GRAVEYARD_SAMPLES_DIR", "").strip()
    return Path(raw) if raw else Path(__file__).resolve().parents[2] / "samples"


def github_token() -> str | None:
    return os.environ.get("GITHUB_TOKEN", "").strip() or None
