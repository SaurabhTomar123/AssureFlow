"""Isolation matrix (P5-05): every API route and every MCP tool, called with another shop's context and with
another practice's context, must be denied (403/404). Prints the matrix and exits non-zero on any leak.

Runs against the test database: python -m scripts.isolation_matrix
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    return subprocess.call(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/offline/test_api.py",
            "tests/offline/test_mcp.py",
            "-k",
            "isolation",
            "-v",
            "-p",
            "no:warnings",
        ],
        cwd=ROOT,
    )


if __name__ == "__main__":
    sys.exit(main())
