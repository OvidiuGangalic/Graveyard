"""Parses a pasted GitHub URL into a validated RepoRef (spec 01, Requirement 1). Pure."""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from graveyard import config
from graveyard.models import IngestError, RepoRef

OWNER_RE = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})")
REPO_RE = re.compile(r"[A-Za-z0-9._-]{1,100}")
HOSTS = frozenset({"github.com", "www.github.com"})
_SSH_PREFIX = "git@github.com:"
_SCHEME_RE = re.compile(r"^([A-Za-z][A-Za-z0-9+.-]*)://")
_GENERIC = "That does not look like a GitHub repo URL. Try https://github.com/owner/repo."
_FOREIGN_HOST = "Only GitHub repos are supported. Try https://github.com/owner/repo."


def _invalid(message: str = _GENERIC) -> IngestError:
    return IngestError("invalid_url", message)


def _split_path(raw: str) -> str:
    """Returns the path of a github.com URL (no query, fragment, credentials or port)."""
    scheme = _SCHEME_RE.match(raw)
    if scheme is not None and scheme.group(1).lower() not in ("http", "https"):
        raise _invalid()
    try:
        parts = urlsplit(raw if scheme else f"https://{raw}")
        host, port = parts.hostname, parts.port
    except ValueError:
        raise _invalid() from None
    if "@" in parts.netloc or port is not None or ":" in parts.netloc:
        raise _invalid()
    if host is None or host.lower() not in HOSTS:
        raise _invalid(_FOREIGN_HOST)
    return parts.path


def parse_repo_url(raw: str) -> RepoRef:
    text = raw.strip()
    if not text or len(text) > config.MAX_URL_LENGTH or re.search(r"\s", text):
        raise _invalid()
    if text.lower().startswith(_SSH_PREFIX):
        path = "/" + text[len(_SSH_PREFIX) :].split("?", 1)[0].split("#", 1)[0]
    else:
        path = _split_path(text)
    segments = path.split("/")[1:]
    if len(segments) < 2:
        raise _invalid()
    owner, repo = segments[0], segments[1].removesuffix(".git")
    # A repo that still ends in ".git" would not survive a round trip through canonical_url.
    if repo in (".", "..") or repo.endswith(".git"):
        raise _invalid()
    if not OWNER_RE.fullmatch(owner) or not REPO_RE.fullmatch(repo):
        raise _invalid()
    return RepoRef(owner=owner, repo=repo)
