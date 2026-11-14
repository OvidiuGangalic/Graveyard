"""GitHub API size pre-check (spec 01, Requirement 3)."""

from __future__ import annotations

import logging

import httpx

from graveyard import config
from graveyard.models import IngestError, RepoRef

log = logging.getLogger(__name__)

SKIPPED_WARNING = "Size pre-check skipped: GitHub API unavailable"


def fetch_repo_size_kb(ref: RepoRef, client: httpx.Client | None = None) -> int | None:
    """Repo size in KB from one API call, or None if it cannot be had for any reason."""
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "graveyard"}
    if token := config.github_token():
        headers["Authorization"] = f"Bearer {token}"
    url = f"https://api.github.com/repos/{ref.owner}/{ref.repo}"
    own = client is None
    http = client or httpx.Client()
    try:
        resp = http.get(url, headers=headers, timeout=config.GITHUB_API_TIMEOUT_S)
        if resp.status_code != 200:
            log.debug("GitHub API status %s", resp.status_code)
            return None
        size = resp.json().get("size")
    except Exception as exc:  # any failure just skips the pre-check
        log.debug("GitHub API call failed: %r", exc)
        return None
    finally:
        if own:
            http.close()
    return size if isinstance(size, int) and not isinstance(size, bool) and size >= 0 else None


def check_size(ref: RepoRef, size_kb: int | None) -> list[str]:
    """Warnings for the analysis; raises ``repo_too_large`` when a limit is set and exceeded."""
    if size_kb is None:
        return [SKIPPED_WARNING]
    limit = config.MAX_REPO_SIZE_KB
    if limit is not None and size_kb > limit:
        raise IngestError(
            "repo_too_large",
            f"This repo is {size_kb // 1024} MB. Graveyard can dig up repos of up to "
            f"{limit // 1024} MB.",
        )
    return []
