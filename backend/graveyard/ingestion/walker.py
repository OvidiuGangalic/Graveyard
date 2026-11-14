"""Lists the files an analysis reads. Pure function of the file tree (spec 01, Requirement 5)."""

from __future__ import annotations

import fnmatch
import os
from pathlib import Path, PurePosixPath

from graveyard import config
from graveyard.models import IngestError, Language, SourceFile, WalkResult

SOURCE_EXTENSIONS: dict[str, Language] = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "typescript",
    ".jsx": "typescript",
    ".mjs": "typescript",
    ".cjs": "typescript",
}

EXCLUDED_DIRS = frozenset(
    {
        ".git",
        "node_modules",
        "vendor",
        "third_party",
        "dist",
        "build",
        "out",
        ".next",
        ".nuxt",
        "coverage",
        "__pycache__",
        ".venv",
        "venv",
        "env",
        ".tox",
        ".mypy_cache",
        "site-packages",
        "migrations",
        "__generated__",
        "generated",
    }
)

EXCLUDED_FILE_PATTERNS = (
    "*.min.js",
    "*.d.ts",
    "*.bundle.js",
    "*_pb2.py",
    "*_pb2_grpc.py",
    "*.config.js",
    "*.config.ts",
    "*.config.mjs",
    "*.config.cjs",
    "*.stories.*",
)

TEXT_EXTENSIONS = frozenset(
    {
        ".yaml",
        ".yml",
        ".toml",
        ".json",
        ".cfg",
        ".ini",
        ".html",
        ".jinja",
        ".j2",
        ".vue",
        ".svelte",
        ".astro",
        ".mdx",
    }
)

PY_TEST_SEGMENTS = frozenset({"tests", "test"})
TS_TEST_SEGMENTS = frozenset({"__tests__", "__mocks__", "e2e", "cypress", "tests", "test"})
GENERATED_MARKERS = (b"@generated", b"DO NOT EDIT")


def is_test_path(path: str, language: Language) -> bool:
    parts = PurePosixPath(path).parts
    name = parts[-1]
    folders = parts[:-1]
    if language == "python":
        return (
            fnmatch.fnmatchcase(name, "test_*.py")
            or fnmatch.fnmatchcase(name, "*_test.py")
            or name == "conftest.py"
            or any(part in PY_TEST_SEGMENTS for part in folders)
        )
    return (
        fnmatch.fnmatchcase(name, "*.test.*")
        or fnmatch.fnmatchcase(name, "*.spec.*")
        or any(part in TS_TEST_SEGMENTS for part in folders)
    )


def _looks_generated(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            head = b"".join(handle.readline(4096) for _ in range(5))
    except OSError:
        return False
    return any(marker in head for marker in GENERATED_MARKERS)


def walk(
    root: Path,
    *,
    max_source_files: int | None = config.MAX_SOURCE_FILES,
    max_file_bytes: int | None = config.MAX_FILE_BYTES,
) -> WalkResult:
    root = Path(root)
    real_root = os.path.realpath(root)
    sources: list[SourceFile] = []
    texts: list[str] = []
    skipped = 0

    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = sorted(
            d
            for d in dirnames
            if d not in EXCLUDED_DIRS and not os.path.islink(os.path.join(dirpath, d))
        )
        for filename in sorted(filenames):
            full = Path(dirpath) / filename
            if full.is_symlink() or not full.is_file():
                continue
            real = os.path.realpath(full)
            if os.path.commonpath([real_root, real]) != real_root:
                continue
            rel = full.relative_to(root).as_posix()
            ext = full.suffix.lower()
            try:
                size = full.stat().st_size
            except OSError:
                continue

            if ext in SOURCE_EXTENSIONS:
                if any(fnmatch.fnmatchcase(filename, p) for p in EXCLUDED_FILE_PATTERNS):
                    continue
                if _looks_generated(full):
                    continue
                if max_file_bytes is not None and size > max_file_bytes:
                    skipped += 1
                    continue
                language = SOURCE_EXTENSIONS[ext]
                sources.append(SourceFile(rel, language, size, is_test_path(rel, language)))
            elif ext in TEXT_EXTENSIONS:
                if filename == "package-lock.json" or filename.endswith(".lock"):
                    continue
                if size > config.MAX_TEXT_FILE_BYTES:
                    continue
                texts.append(rel)

    if max_source_files is not None and len(sources) > max_source_files:
        raise IngestError(
            "too_many_files",
            f"This repo has {len(sources):,} source files. "
            f"Graveyard can dig through up to {max_source_files:,}.",
        )

    sources.sort(key=lambda f: f.path)
    texts.sort()
    return WalkResult(tuple(sources), tuple(texts), skipped)


def read_text(root: Path, rel_path: str) -> str:
    """Read a repo file as text. Never fails on bad encoding (Requirement 7.3)."""
    try:
        return (Path(root) / rel_path).read_bytes().decode("utf-8", errors="replace")
    except OSError:
        return ""
