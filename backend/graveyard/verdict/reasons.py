# ruff: noqa: E501  (templates are verbatim one-line sentences)
"""One-sentence reasons for each verdict row (design: "Reason templates")."""

import logging
from collections.abc import Mapping
from datetime import datetime

from graveyard.models import Candidate, CommitInfo, Flag

log = logging.getLogger(__name__)

# Tests set this to True so an unknown reason ID raises; production logs and falls back.
STRICT = False

FALLBACK = "No references were found."
MAX_LEN = 240
MAX_DETAIL = 60
MAX_LOC = 80

TEMPLATES: Mapping[str, str] = {
    "RV_DYNAMIC_IMPORT": "Its file is loaded with a dynamic import at {loc}, so it is probably used at runtime.",
    "RV_DUNDER_ALL": "It is listed in `__all__` at {loc}, so it is part of the public API and may be used by code outside this repo.",
    "RV_LIBRARY_API": "It is exported from a published package ({detail}), and code outside this repo may import it, which this analysis cannot see.",
    "RV_STRING_MATCH": "Nothing calls it directly, but its name appears as a string at {loc}, which suggests it is looked up by name at runtime.",
    "UN_DECORATOR": "Nothing calls it directly, but the decorator `{detail}` may register it with a framework, which static analysis cannot confirm.",
    "UN_BASE_CLASS": "Nothing calls it directly, but its class extends `{detail}` from outside this repo, which may call this method itself.",
    "UN_SCRIPT_GLOBAL": "Nothing calls it, but this file is a plain script whose functions are global and may be called from HTML or other scripts.",
    "BM_EXPORTED": "It is exported but nothing in this repo imports it, so it is safe to delete unless code outside this repo uses it.",
    "BM_DYNAMIC_FILE": "No references were found, but its file uses dynamic lookups ({detail}), so a call at runtime cannot be ruled out.",
    "BM_REFLECTION": "No references were found, but this repo calls methods by computed name, so a call at runtime cannot be ruled out.",
    "BM_ARITY": "Other code calls something with this name at {detail}, but with arguments this definition cannot accept, so that call is taken to mean a different function.",
    "BM_SIDE_EFFECT": "It is never used in this file, but importing `{detail}` may have side effects, so check before removing it.",
    "BM_CONDITIONAL": "It is never used in this file, but it is imported conditionally, which is often a deliberate availability check.",
    "BM_TEST_ONLY": "Only tests reference it ({n} place(s), first at {loc}), so delete it together with those tests.",
    "BM_NO_HISTORY": "No references were found, but its age is unknown because git history was unavailable.",
    "BM_SHALLOW_HISTORY": "No references were found, but the available git history only shows it is {age} days old.",
    "BM_RECENT": "No references were found, but it was touched {age} days ago, so it may be work in progress.",
    "BH_FUNCTION": "No references anywhere in this repo, no test mentions it, it has been untouched for {age} days, and its file has no dynamic lookups.",
    "BH_IMPORT": "It is never used in this file, it has been untouched for {age} days, and the file has no dynamic lookups.",
    # P1 only (zombie tests); the design lists the IDs but gives no wording, so this is provisional.
    "BM_ZOMBIE_SKIPPED": "This test is permanently skipped, so it never runs and guards nothing.",
    "BM_ZOMBIE_EMPTY": "This test has no assertions, so it passes without checking anything.",
}

# Which flag's detail fills {detail} for each reason.
_DETAIL_FLAG: Mapping[str, Flag] = {
    "RV_LIBRARY_API": Flag.LIBRARY_API,
    "UN_DECORATOR": Flag.UNKNOWN_DECORATOR,
    "UN_BASE_CLASS": Flag.EXTERNAL_BASE_CLASS,
    "BM_DYNAMIC_FILE": Flag.DYNAMIC_PATTERN_IN_FILE,
    "BM_ARITY": Flag.ARITY_MISMATCH,
    "BM_SIDE_EFFECT": Flag.SIDE_EFFECT_IMPORT,
}

# Which caller kind gives {loc} for each reason.
_LOC_KIND: Mapping[str, str] = {
    "RV_DYNAMIC_IMPORT": "dynamic_import",
    "RV_DUNDER_ALL": "reexport",
    "RV_STRING_MATCH": "string_match",
    "BM_TEST_ONLY": "test_reference",
}


def _clean(text: str) -> str:
    """One line, no braces (they would look like unreplaced placeholders)."""
    return " ".join(text.replace("{", "").replace("}", "").split())


def _loc(reason_id: str, c: Candidate) -> str | None:
    kind = _LOC_KIND.get(reason_id)
    for caller in c.callers:
        if caller.kind == kind:
            loc = _clean(f"{caller.file_path}:{caller.line}")
            return loc if len(loc) <= MAX_LOC else "..." + loc[-(MAX_LOC - 3) :]
    return None


def _age(commit: CommitInfo | None, created_at: datetime) -> str:
    if commit is None:
        return "an unknown number of"
    days = max(0, (created_at - commit.date).days)
    return f"at least {days}" if commit.is_boundary else str(days)


def render(reason_id: str, c: Candidate, commit: CommitInfo | None, created_at: datetime) -> str:
    template = TEMPLATES.get(reason_id)
    if template is None:
        if STRICT:
            raise KeyError(reason_id)
        log.error("unknown reason id %r", reason_id)
        return FALLBACK

    loc = _loc(reason_id, c)
    text = template.replace("at {loc}", f"at {loc}" if loc else "in this repo")
    flag = _DETAIL_FLAG.get(reason_id)
    detail = _clean(c.flag_details.get(flag, ""))[:MAX_DETAIL].strip() if flag else ""
    if reason_id == "BM_ARITY" and not detail:
        text = text.replace("at {detail}", "in this repo")
    text = text.replace("{detail}", detail or "unspecified")
    n = sum(1 for caller in c.callers if caller.kind == "test_reference")
    text = text.replace("{n}", str(n)).replace("{age}", _age(commit, created_at))

    if len(text) > MAX_LEN:  # defensive: loc and detail are already capped
        text = text[: MAX_LEN - 1].rstrip() + "."
    return text
