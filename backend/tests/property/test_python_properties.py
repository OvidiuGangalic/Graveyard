import tempfile
from dataclasses import replace
from pathlib import Path

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st
from strategies import exempt_function, identifier, python_repo

from graveyard.analyzers.python.analyser import analyse_python
from graveyard.ingestion import ingest_local

REPO = settings(max_examples=40)


def analyse(files: dict[str, str], **kw):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for rel, text in files.items():
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            (root / rel).write_bytes(text.encode())
        snap = ingest_local(root)
        return snap, analyse_python(snap, **kw)


def funcs(result) -> set[tuple[str, str]]:
    return {(c.file_path, c.name) for c in result.candidates if c.kind == "function"}


def keys(result) -> set[tuple[str, str, str]]:
    return {(c.file_path, c.qualified_name, c.kind) for c in result.candidates}


def stem(path: str) -> str:
    return path.removesuffix(".py").replace("/", ".")


@pytest.mark.property
@settings(max_examples=100)
@given(st.one_of(st.text(), st.binary().map(lambda b: b.decode("utf-8", "replace"))))
def test_p1_never_crashes(text):
    """P1 (never crashes). For any text (Hypothesis `text()` and `binary()` decoded with
    replacement) placed in a `.py` file, `analyse_python` returns without raising.

    **Validates: Requirement 7.1.**
    """
    analyse({"m.py": text})


@pytest.mark.property
@REPO
@given(python_repo(unique=False))
def test_p2_bounded_and_well_formed(repo):
    """P2 (bounded and well-formed). For any generated repo, the number of function Candidates
    is <= `functions_defined`; every Candidate has `1 <= start_line <= end_line <=` the file's
    line count; `code_snippet` equals those lines.

    **Validates: Requirements 1.1, 8.1.**
    """
    _, result = analyse(repo.files)
    assert sum(c.kind == "function" for c in result.candidates) <= result.functions_defined
    for c in result.candidates:
        lines = repo.files[c.file_path].split("\n")
        assert 1 <= c.start_line <= c.end_line <= len(lines)
        assert c.code_snippet == "\n".join(lines[c.start_line - 1 : c.end_line])


@pytest.mark.property
@REPO
@given(python_repo())
def test_p3_caller_flips_result(repo):
    """P3 (a caller flips the result). For any generated repo with an uncalled, non-exempt
    function `f` in module `m`: `f` is reported. Adding `from m import f` and `f()` to another
    production module makes `f` unreported. Removing both again makes `f` reported.

    **Validates: Requirements 2.2, 2.4.**
    """
    assume(repo.uncalled)
    path, name = repo.uncalled[0]
    assert (path, name) in funcs(analyse(repo.files)[1])
    with_caller = {**repo.files, "zz_caller.py": f"from {stem(path)} import {name}\n\n{name}()\n"}
    assert (path, name) not in funcs(analyse(with_caller)[1])
    assert (path, name) in funcs(analyse(repo.files)[1])


@pytest.mark.property
@REPO
@given(python_repo(), python_repo(unique=False))
def test_p5_adding_files_never_kills(repo, extra):
    """P5 (adding files never kills). For any generated repo `R` and any extra generated Python
    file `x`, every function Candidate of `R and x` located in `R`'s files is also a Candidate
    of `R`.

    **Validates: Requirement 2.1.**
    """
    more = {**repo.files, **{f"extra/{p}": s for p, s in extra.files.items()}}
    before = funcs(analyse(repo.files)[1])
    after = {f for f in funcs(analyse(more)[1]) if f[0] in repo.files}
    assert after <= before


@pytest.mark.property
@REPO
@given(python_repo(), exempt_function(), st.data())
def test_p6_exempt_never_reported(repo, exempt, data):
    """P6 (exempt names are never reported). For any generated function given a name or
    decorator drawn from the PY-E tables, it is not reported, whatever the call graph.

    **Validates: Requirement 3.2.**
    """
    name, source = exempt
    path = data.draw(st.sampled_from(sorted(repo.files)))
    files = {**repo.files, path: repo.files[path] + "\n\n" + source}
    assert (path, name) not in funcs(analyse(files)[1])


@pytest.mark.property
@REPO
@given(python_repo(), st.data())
def test_p13_using_an_import_revives_it(repo, data):
    """P13 (using an import revives it). For any generated module with an unused
    `from m import n`, `n` is reported; appending a statement that reads `n` makes it
    unreported.

    **Validates: Requirement 6.1.**
    """
    path, name = data.draw(st.sampled_from(repo.functions))
    src = f"from {stem(path)} import {name}\n"

    def dead(text):
        result = analyse({**repo.files, "user.py": text})[1]
        return any(c.kind == "import" and c.file_path == "user.py" for c in result.candidates)

    assert dead(src)
    assert not dead(src + f"\nvalue = {name}\n")


@pytest.mark.property
@REPO
@given(python_repo(unique=False), st.randoms(use_true_random=False))
def test_p4a_deterministic_under_shuffle(repo, rnd):
    """P4a (deterministic). Shuffling the order of `source_files` in the snapshot does not
    change the returned list.

    **Validates: Requirements 7.2, 7.3.**
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for rel, text in repo.files.items():
            (root / rel).write_text(text)
        snap = ingest_local(root)
        shuffled = list(snap.source_files)
        rnd.shuffle(shuffled)
        again = analyse_python(replace(snap, source_files=tuple(shuffled)))
        assert again.candidates == analyse_python(snap).candidates


@pytest.mark.property
@REPO
@given(identifier(), st.booleans())
def test_p24_same_name_different_module(name, first):
    """P24 (same name, different module). For any generated repo in which two modules each
    define a function `f`, and a third module imports and calls exactly one of them: exactly the
    other one is reported. Switching the import to the other module switches the result.

    **Validates: Requirement 2.4.**
    """
    base = {f"{m}.py": f"def {name}():\n    return {i}\n" for i, m in enumerate(("ma", "mb"))}
    order = (("ma", "mb"), ("mb", "ma")) if first else (("mb", "ma"), ("ma", "mb"))
    for used, other in order:
        files = {**base, "caller.py": f"from {used} import {name}\n\n{name}()\n"}
        assert funcs(analyse(files)[1]) == {(f"{other}.py", name)}


@pytest.mark.property
@REPO
@given(python_repo(unique=False))
def test_p25_resolution_only_adds(repo):
    """P25 (resolution only adds). For any generated repo, every function reported with
    `resolve_all_unresolved=True` is also reported by the normal analysis.

    **Validates: Requirements 2.9, 2.10.**
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for rel, text in repo.files.items():
            (root / rel).write_text(text)
        snap = ingest_local(root)
        assert keys(analyse_python(snap, resolve_all_unresolved=True)) <= keys(analyse_python(snap))
