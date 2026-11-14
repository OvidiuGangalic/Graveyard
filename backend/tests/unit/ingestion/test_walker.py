from pathlib import Path

import pytest

from graveyard.ingestion.walker import EXCLUDED_DIRS, read_text, walk
from graveyard.models import IngestError, WalkResult


def make(root: Path, files: dict[str, str | bytes]) -> Path:
    for rel, body in files.items():
        f = root / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(body if isinstance(body, bytes) else body.encode())
    return root


def paths(root: Path, **kw) -> list[str]:
    return [f.path for f in walk(root, **kw).source_files]


@pytest.mark.parametrize("d", sorted(EXCLUDED_DIRS))
def test_excluded_dirs(tmp_path, d):
    make(tmp_path, {f"{d}/a.py": "x=1", f"src/{d}/b.py": "x=1", "ok.py": "x=1"})
    assert paths(tmp_path) == ["ok.py"]


@pytest.mark.parametrize(
    "name",
    "a.min.js a.d.ts a.bundle.js a_pb2.py a_pb2_grpc.py x.config.js x.config.ts x.config.mjs "
    "x.config.cjs a.stories.tsx".split(),
)
def test_excluded_file_patterns(tmp_path, name):
    make(tmp_path, {name: "x", "ok.py": "x"})
    assert paths(tmp_path) == ["ok.py"]


@pytest.mark.parametrize(
    ("body", "excluded"),
    [("# @generated\nx=1", True), ("# DO NOT EDIT\nx=1", True),
     ("\n" * 4 + "# @generated\n", True), ("\n" * 5 + "# @generated\n", False)],
)  # fmt: skip
def test_generated_header_in_first_five_lines(tmp_path, body, excluded):
    make(tmp_path, {"g.py": body})
    assert (paths(tmp_path) == []) is excluded


def test_language_classification(tmp_path):
    names = ["a.py", "b.ts", "c.jsx", "d.mjs", "e.cjs"]
    make(tmp_path, dict.fromkeys([*names, "f.txt"], "x"))
    got = {f.path: f.language[0] for f in walk(tmp_path).source_files}
    assert got == {n: "p" if n == "a.py" else "t" for n in names}


@pytest.mark.parametrize(
    ("path", "is_test"),
    [("test_a.py", True), ("a_test.py", True), ("conftest.py", True), ("tests/a.py", True),
     ("x/test/a.py", True), ("src/testing/util.py", False), ("contest.py", False),
     ("a.test.ts", True), ("a.spec.js", True), ("__tests__/a.ts", True),
     ("__mocks__/a.ts", True), ("e2e/a.ts", True), ("cypress/a.ts", True),
     ("x/test/a.ts", True), ("src/testing/a.ts", False), ("latest.ts", False)],
)  # fmt: skip
def test_is_test(tmp_path, path, is_test):
    make(tmp_path, {path: "x"})
    (f,) = walk(tmp_path).source_files
    assert f.is_test is is_test


def test_text_references(tmp_path):
    big = b"x" * 1024 * 1024
    make(tmp_path, {"a.yaml": "x", "package-lock.json": "x", "c.lock": "x", "ok.json": big,
                    "big.json": big + b"x"})  # fmt: skip
    assert walk(tmp_path).text_files == ("a.yaml", "ok.json")


def test_max_file_bytes_counts_skipped(tmp_path):
    make(tmp_path, {"a.py": "x" * 10, "b.py": "x"})
    r = walk(tmp_path, max_file_bytes=5)
    assert [f.path for f in r.source_files] == ["b.py"] and r.files_skipped == 1


def test_max_source_files(tmp_path):
    make(tmp_path, {"a.py": "x", "b.py": "x", "c.py": "x"})
    with pytest.raises(IngestError) as err:
        walk(tmp_path, max_source_files=2)
    assert err.value.code == "too_many_files"
    assert "3" in err.value.message and "2" in err.value.message


def test_empty_repo(tmp_path):
    assert walk(tmp_path) == WalkResult((), (), 0)


def test_read_text_bad_encoding(tmp_path):
    assert "x" in read_text(make(tmp_path, {"a.py": b"x\xff"}), "a.py")
