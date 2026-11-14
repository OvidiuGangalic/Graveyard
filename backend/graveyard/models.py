"""Shared types.

Internal pipeline types are frozen dataclasses; everything that crosses the HTTP API is
a Pydantic model. Pipeline stages talk to each other only through these types.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

Language = Literal["python", "typescript"]
Kind = Literal["function", "import", "test"]
Coverage = Literal["covered", "not_covered", "unknown"]
Confidence = Literal["high", "medium", "low"]
Verdict = Literal["bury", "revive", "unsure"]
CallerKind = Literal["test_reference", "string_match", "dynamic_import", "reexport"]
Status = Literal["queued", "running", "done", "failed"]
Phase = Literal[
    "queued", "cloning", "scanning", "python", "typescript", "history", "verdicts", "done"
]


# --------------------------------------------------------------------------- errors


class IngestError(Exception):
    """The only exception ingestion raises on purpose. ``message`` is written for users."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class AnalysisTimeout(Exception):
    """The pipeline deadline passed."""


class PipelineError(Exception):
    def __init__(self, code: str, message: str = "Something went wrong while digging.") -> None:
        super().__init__(message)
        self.code = code
        self.message = message


# --------------------------------------------------------------------------- ingestion


@dataclass(frozen=True)
class RepoRef:
    owner: str
    repo: str

    @property
    def canonical_url(self) -> str:
        return f"https://github.com/{self.owner}/{self.repo}"

    @property
    def clone_url(self) -> str:
        return f"https://github.com/{self.owner}/{self.repo}.git"

    @property
    def repo_name(self) -> str:
        return f"{self.owner}/{self.repo}"


@dataclass(frozen=True)
class RemoteHead:
    branch: str
    commit: str


@dataclass(frozen=True)
class SourceFile:
    path: str  # POSIX-style, relative to repo root
    language: Language
    size_bytes: int
    is_test: bool


@dataclass(frozen=True)
class WalkResult:
    source_files: tuple[SourceFile, ...]
    text_files: tuple[str, ...]
    files_skipped: int


@dataclass(frozen=True)
class RepoSnapshot:
    root: Path
    repo_url: str  # canonical URL, or "sample://haunted-repo"
    repo_name: str
    branch: str
    commit: str  # 40-hex, or "" when there is no git history
    is_sample: bool
    has_git: bool
    history_depth: int | None  # CLONE_DEPTH for shallow clones, None for full history
    source_files: tuple[SourceFile, ...]  # sorted by path
    text_files: tuple[str, ...]  # sorted
    files_skipped: int
    warnings: tuple[str, ...] = ()


# --------------------------------------------------------------------------- analyser contract


class Flag(StrEnum):
    # positive evidence of use -> verdict revive
    STRING_MATCH = "string_match"
    IN_DUNDER_ALL = "in_dunder_all"
    LIBRARY_API = "library_api"  # TS only
    DYNAMIC_IMPORT = "dynamic_import"  # TS only
    # analysis is blind here -> verdict unsure
    UNKNOWN_DECORATOR = "unknown_decorator"
    EXTERNAL_BASE_CLASS = "external_base_class"
    SCRIPT_GLOBAL = "script_global"  # TS only
    # caps confidence at medium
    EXPORTED = "exported"  # TS only
    DYNAMIC_PATTERN_IN_FILE = "dynamic_pattern_in_file"
    REPO_HAS_REFLECTION = "repo_has_reflection"
    ARITY_MISMATCH = "arity_mismatch"
    SIDE_EFFECT_IMPORT = "side_effect_import"
    CONDITIONAL_IMPORT = "conditional_import"
    # informational
    PARTIAL_STATEMENT = "partial_statement"
    ZOMBIE_SKIPPED = "zombie_skipped"  # P1
    ZOMBIE_EMPTY = "zombie_empty"  # P1


REVIVE_FLAGS = frozenset(
    {Flag.DYNAMIC_IMPORT, Flag.IN_DUNDER_ALL, Flag.LIBRARY_API, Flag.STRING_MATCH}
)
BLIND_FLAGS = frozenset({Flag.UNKNOWN_DECORATOR, Flag.EXTERNAL_BASE_CLASS, Flag.SCRIPT_GLOBAL})
CAUTION_FLAGS = frozenset(
    {
        Flag.EXPORTED,
        Flag.DYNAMIC_PATTERN_IN_FILE,
        Flag.REPO_HAS_REFLECTION,
        Flag.ARITY_MISMATCH,
        Flag.SIDE_EFFECT_IMPORT,
        Flag.CONDITIONAL_IMPORT,
    }
)


@dataclass(frozen=True)
class Caller:
    file_path: str
    line: int
    kind: CallerKind
    snippet: str  # the source line, stripped, max 200 chars


@dataclass(frozen=True)
class Candidate:
    name: str  # "recount", "json"
    qualified_name: str  # "Stock.recount"
    kind: Kind
    language: Language
    file_path: str
    start_line: int  # 1-based, inclusive
    end_line: int
    code_snippet: str
    snippet_truncated: bool
    callers: tuple[Caller, ...] = ()
    test_coverage: Coverage = "unknown"
    flags: frozenset[Flag] = frozenset()
    flag_details: Mapping[Flag, str] = field(default_factory=dict)

    def __hash__(self) -> int:  # flag_details is a dict; identity is the location
        return hash((self.language, self.file_path, self.start_line, self.qualified_name))


@dataclass(frozen=True)
class AnalyserResult:
    candidates: tuple[Candidate, ...]
    functions_defined: int
    files_parsed: int
    files_failed: int
    warnings: tuple[str, ...] = ()


# progress(phase, files_done): called by stages; must be cheap and must not raise.
ProgressFn = Callable[[str, int], None]


def no_progress(phase: str, files_done: int) -> None:
    return None


@dataclass(frozen=True)
class CommitInfo:
    hash: str
    date: datetime  # timezone-aware, UTC
    author: str
    is_boundary: bool = False


# --------------------------------------------------------------------------- API models


class LastCommit(BaseModel):
    hash: str
    date: datetime
    author: str
    is_boundary: bool = False


class CallerFound(BaseModel):
    file_path: str
    line: int
    kind: CallerKind
    snippet: str


class DeadItem(BaseModel):
    id: str
    name: str
    kind: Kind
    language: Language
    file_path: str
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    last_commit: LastCommit | None = None
    age_days: int | None = None
    callers_found: list[CallerFound] = Field(default_factory=list)
    test_coverage: Coverage = "unknown"
    confidence: Confidence
    verdict: Verdict
    verdict_reason: str
    code_snippet: str
    snippet_truncated: bool = False
    deletable_as_whole_lines: bool = True


class Progress(BaseModel):
    phase: Phase = "queued"
    files_discovered: int = 0
    queue_position: int = 0


class Analysis(BaseModel):
    id: str
    repo_url: str
    repo_name: str
    branch: str
    commit_analysed: str
    status: Status = "queued"
    created_at: datetime
    total_files_scanned: int = 0
    total_dead_items: int = 0
    items_by_language: dict[str, int] = Field(
        default_factory=lambda: {"python": 0, "typescript": 0}
    )
    items_by_verdict: dict[str, int] = Field(
        default_factory=lambda: {"bury": 0, "revive": 0, "unsure": 0}
    )
    error_message: str | None = None
    error_code: str | None = None
    progress: Progress = Field(default_factory=Progress)
    is_sample: bool = False
    expires_at: datetime | None = None
    warnings: list[str] = Field(default_factory=list)


class ItemsResponse(BaseModel):
    analysis_id: str
    total: int
    returned: int
    items: list[DeadItem]
