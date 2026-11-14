"""The one function the CLI, the tests and the API all call: snapshot in, analysis out."""

from __future__ import annotations

import logging
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime

from graveyard import config
from graveyard.analyzers.python.analyser import analyse_python
from graveyard.git.archaeology import candidate_key, dig
from graveyard.models import (
    AnalyserResult,
    AnalysisTimeout,
    DeadItem,
    IngestError,
    PipelineError,
    ProgressFn,
    RepoSnapshot,
    no_progress,
)
from graveyard.verdict.engine import assemble, finalise, judge

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class PipelineResult:
    items: tuple[DeadItem, ...]
    total_files_scanned: int
    files_skipped: int
    items_by_language: dict[str, int]
    items_by_verdict: dict[str, int]
    total_dead_items: int
    warnings: tuple[str, ...]


def _analyse_typescript(
    snapshot: RepoSnapshot, progress: ProgressFn, deadline: float | None
) -> AnalyserResult:
    # TODO(spec 03): replace with analyse_typescript
    return AnalyserResult(candidates=(), functions_defined=0, files_parsed=0, files_failed=0)


def run(
    snapshot: RepoSnapshot,
    created_at: datetime,
    progress: ProgressFn = no_progress,
    deadline: float | None = None,
) -> PipelineResult:
    if deadline is None and config.ANALYSIS_TIMEOUT_S is not None:
        deadline = time.monotonic() + config.ANALYSIS_TIMEOUT_S
    try:
        python = analyse_python(snapshot, progress, deadline)
        typescript = _analyse_typescript(snapshot, progress, deadline)
        candidates = sorted(
            (*python.candidates, *typescript.candidates),
            key=lambda c: (c.file_path, c.start_line, c.qualified_name),
        )

        def history_progress(_phase: str, done: int) -> None:
            progress("history", done)  # archaeology reports its own phase name

        history = dig(snapshot, candidates, created_at, history_progress)
        progress("verdicts", 0)
        built: list[DeadItem] = []
        for done, c in enumerate(candidates, 1):
            commit = history.commits.get(candidate_key(c))
            built.append(assemble(c, commit, judge(c, commit, created_at), created_at))
            progress("verdicts", done)
        items, cap_warnings = finalise(built)
    except (AnalysisTimeout, IngestError):
        raise
    except Exception as exc:
        log.exception("pipeline stage failed")
        raise PipelineError("internal_error") from exc

    skipped = snapshot.files_skipped + python.files_failed + typescript.files_failed
    warnings = [
        *snapshot.warnings,
        *python.warnings,
        *typescript.warnings,
        *history.warnings,
        *cap_warnings,
    ]
    if skipped > 0:
        warnings.append(f"{skipped} files skipped: too large or not parseable")
    return PipelineResult(
        items=tuple(items),
        total_files_scanned=len(snapshot.source_files),
        files_skipped=skipped,
        items_by_language={"python": 0, "typescript": 0, **Counter(i.language for i in built)},
        items_by_verdict={"bury": 0, "revive": 0, "unsure": 0, **Counter(i.verdict for i in built)},
        total_dead_items=len(built),
        warnings=tuple(dict.fromkeys(warnings)),
    )
