"""Shallow clone into a private directory, with the clone's lifecycle (spec 01, task 10)."""

from __future__ import annotations

import logging
import os
import secrets
import subprocess
from pathlib import Path

from graveyard import config
from graveyard.ingestion.samples import remove_tree
from graveyard.models import IngestError, RepoRef

log = logging.getLogger(__name__)

# Extra `-c key=value` settings. Empty in production; tests add protocol.file.allow=always
# so they can clone local file:// repos. Production never allows the file protocol.
_EXTRA_CONFIG: tuple[str, ...] = ()

_SAFE_CONFIG = (
    "filter.lfs.smudge=",  # no LFS filter command runs on checkout
    "filter.lfs.process=",  # no long-running LFS filter process either
    "filter.lfs.required=false",  # a missing LFS filter must not fail the clone
    "core.fsmonitor=false",  # never launch a repo-named fsmonitor program
)


def clones_dir() -> Path:
    return config.data_dir() / "clones"


def new_clone_dir() -> Path:
    """A fresh directory named by random hex, never by user input (Requirement 7.2)."""
    root = clones_dir()
    root.mkdir(parents=True, exist_ok=True)
    while True:
        path = root / secrets.token_hex(8)
        try:
            path.mkdir()
        except FileExistsError:
            continue
        return path


def _env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(
        GIT_TERMINAL_PROMPT="0",
        GIT_LFS_SKIP_SMUDGE="1",
        GIT_CONFIG_NOSYSTEM="1",
        GIT_CONFIG_GLOBAL=os.devnull,
    )
    return env


def _dir_size_bytes(path: Path) -> int:
    total = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += (Path(root) / name).lstat().st_size
            except OSError:
                pass
    return total


def _unavailable() -> IngestError:
    return IngestError(
        "github_unavailable", "GitHub is not answering right now. Try again shortly."
    )


def shallow_clone(ref: RepoRef, branch: str, dest: Path, url: str | None = None) -> str:
    """Clone ``branch`` at depth ``CLONE_DEPTH`` into ``dest``; return the analysed commit."""
    args = ["git", "--no-pager"]
    for setting in (*_SAFE_CONFIG, *_EXTRA_CONFIG):
        args += ["-c", setting]
    args += [
        "clone",
        "--depth",
        str(config.CLONE_DEPTH),
        "--single-branch",
        "--branch",
        branch,
        "--no-tags",
        "--no-recurse-submodules",
        url or ref.clone_url,
        str(dest),
    ]
    try:
        result = subprocess.run(
            args,
            env=_env(),
            capture_output=True,
            text=True,
            timeout=config.CLONE_TIMEOUT_S,
            stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired:
        remove_tree(dest)
        raise IngestError(
            "clone_timeout",
            f"Cloning took longer than {config.CLONE_TIMEOUT_S} seconds. Try a smaller repo.",
        ) from None
    except OSError:
        log.debug("git could not be started", exc_info=True)
        remove_tree(dest)
        raise _unavailable() from None
    if result.returncode != 0:
        log.debug("git clone failed: %s", result.stderr)
        remove_tree(dest)
        raise _unavailable()

    limit_mb = config.MAX_CLONE_DISK_MB
    if limit_mb is not None:
        size_mb = _dir_size_bytes(dest) / (1024 * 1024)
        if size_mb > limit_mb:
            remove_tree(dest)
            raise IngestError(
                "repo_too_large",
                f"This repo is {size_mb:.0f} MB on disk. Graveyard can dig up repos of up to"
                f" {limit_mb} MB.",
            )

    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=dest,
        env=_env(),
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
    )
    commit = head.stdout.strip()
    if head.returncode != 0 or not commit:
        log.debug("rev-parse failed: %s", head.stderr)
        remove_tree(dest)
        raise _unavailable()
    return commit


def cleanup(dest: Path) -> None:
    remove_tree(dest)


def cleanup_all() -> None:
    """Delete every leftover clone (called at startup, Requirement 4.6)."""
    root = clones_dir()
    if not root.exists():
        return
    for child in root.iterdir():
        if child.is_dir():
            remove_tree(child)
        else:
            child.unlink(missing_ok=True)
