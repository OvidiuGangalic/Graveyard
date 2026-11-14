"""Pre-tool-use guard for the `block-commit-on-failing-properties` hook.

Kiro passes the pending tool call as JSON on stdin. If that call is a
`git commit`, run the property tests and the accuracy gate. A non-zero exit
blocks the tool call; stderr is shown to the agent.

Until the backend tests exist (before spec 01 task 1) the guard lets commits through.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

SUITES = ["backend/tests/property", "backend/tests/acceptance"]


def main() -> int:
    event = sys.stdin.read()
    if not re.search(r"\bgit\b[^\n|;&]*\bcommit\b", event):
        return 0

    suites = [s for s in SUITES if Path(s).is_dir()]
    if not suites:
        return 0

    result = subprocess.run(
        [sys.executable, "-m", "pytest", *suites, "-q", "-x"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0:
        return 0

    tail = "\n".join(result.stdout.splitlines()[-30:])
    sys.stderr.write(
        "Commit blocked: property tests or the accuracy gate are failing.\n"
        "Fix the failure (do not weaken the test), then commit again.\n\n" + tail + "\n"
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
