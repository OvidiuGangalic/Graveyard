"""Talks to the git remote (spec 01, Requirement 2)."""

from __future__ import annotations

import logging
import os
import re
import subprocess

from graveyard import config
from graveyard.models import IngestError, RemoteHead, RepoRef

log = logging.getLogger(__name__)

_NOT_FOUND = ("not found", "authentication", "could not read username", "does not appear to be")
_SYMREF = re.compile(r"^ref:\s*refs/heads/(\S.*?)\tHEAD$")
_SHA = re.compile(r"^([0-9a-f]{40}|[0-9a-f]{64})\tHEAD$")

_UNAVAILABLE = "GitHub is not answering right now. Try again shortly."


def _git_env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(
        GIT_CONFIG_NOSYSTEM="1",
        GIT_CONFIG_GLOBAL=os.devnull,
        GIT_TERMINAL_PROMPT="0",
        GIT_ASKPASS="echo",
        GIT_OPTIONAL_LOCKS="0",
    )
    return env


def ls_remote(ref: RepoRef, url: str | None = None) -> RemoteHead:
    """Return the remote's default branch and head commit without cloning.

    ``url`` exists only so tests can point at a local bare repo.
    """
    try:
        result = subprocess.run(
            [
                "git",
                "-c",
                "credential.helper=",
                "ls-remote",
                "--symref",
                url or ref.clone_url,
                "HEAD",
            ],
            env=_git_env(),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=config.LS_REMOTE_TIMEOUT_S,
            check=False,
            stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
        log.debug("ls-remote failed: %r", exc)
        raise IngestError("github_unavailable", _UNAVAILABLE) from None

    if result.returncode != 0:
        log.debug("ls-remote stderr: %s", result.stderr)
        stderr = result.stderr.lower()
        if any(marker in stderr for marker in _NOT_FOUND):
            raise IngestError(
                "repo_not_found_or_private",
                "That repo is private or does not exist. Graveyard can only dig in public repos.",
            )
        raise IngestError("github_unavailable", _UNAVAILABLE)

    branch: str | None = None
    commit: str | None = None
    for line in result.stdout.splitlines():
        if m := _SYMREF.match(line):
            branch = m.group(1)
        elif m := _SHA.match(line):
            commit = m.group(1)
    if branch is None or commit is None:
        raise IngestError("repo_empty", "This repo has no commits yet.")
    return RemoteHead(branch=branch, commit=commit)
