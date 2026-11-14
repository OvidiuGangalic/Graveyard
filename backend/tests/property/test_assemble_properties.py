import re
from datetime import UTC, datetime

from hypothesis import given
from hypothesis import strategies as st

from graveyard.models import Candidate
from graveyard.verdict.engine import Judgement, assemble, finalise

NOW = datetime(2026, 11, 15, tzinfo=UTC)


@st.composite
def candidates(draw):
    return Candidate(
        name="f",
        qualified_name=draw(st.sampled_from(["f", "A.f", "g"])),
        kind=draw(st.sampled_from(["function", "import"])),
        language=draw(st.sampled_from(["python", "typescript"])),
        file_path=draw(st.sampled_from(["a.py", "b.py"])),
        start_line=draw(st.integers(1, 3)),
        end_line=3,
        code_snippet="x",
        snippet_truncated=False,
    )


@given(st.lists(candidates(), max_size=40))
def test_ids_unique_and_hex(cands):
    """P18 (ids are unique). Item ids are pairwise distinct after finalise, even for duplicate keys.

    **Validates: Requirement 4.3.**
    """
    j = Judgement("high", "bury", "BH_FUNCTION")
    items, _ = finalise([assemble(c, None, j, NOW) for c in cands])
    ids = [i.id for i in items]
    assert len(items) == len(cands)
    assert len(set(ids)) == len(ids)
    assert all(re.fullmatch(r"[0-9a-f]{12}", i) for i in ids)
