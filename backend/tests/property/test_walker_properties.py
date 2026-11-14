import os
import tempfile
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from graveyard.ingestion.walker import EXCLUDED_DIRS, walk

SEGMENT = st.sampled_from(["src", "lib", "a", "node_modules", "build", "venv", ".git", "vendor"])
NAME = st.sampled_from(["m.py", "x.ts", "c.yaml", "n.min.js"])


@pytest.mark.property
@settings(max_examples=50)
@given(st.lists(st.tuples(st.lists(SEGMENT, max_size=3), NAME), max_size=8))
def test_p14_walker_containment(tree):
    """P14 (walker containment). For any generated file tree, every path in `WalkResult`
    resolves inside the root and none has an excluded directory segment.

    **Validates: Requirements 5.1, 5.2.**
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp).resolve()
        for segs, name in tree:
            f = root.joinpath(*segs, name)
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text("x")
        result = walk(root)
        for rel in [*(f.path for f in result.source_files), *result.text_files]:
            assert os.path.commonpath([root, (root / rel).resolve()]) == str(root)
            assert not set(Path(rel).parts[:-1]) & EXCLUDED_DIRS
