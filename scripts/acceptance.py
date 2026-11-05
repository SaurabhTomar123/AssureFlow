"""Offline acceptance run with a machine-generated report (spec section 12; hackathon cut of P5-09).

Writes docs/release/acceptance-<run_id>.json with run id, environment, pinned Switch versions, commit,
fixture version, assertions, failures and the report hash. Run: python -m scripts.acceptance
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import uuid
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    run_id = uuid.uuid4().hex[:12]
    out = ROOT / "docs" / "release"
    out.mkdir(parents=True, exist_ok=True)
    junit = out / f"junit-{run_id}.xml"
    code = subprocess.call(
        [sys.executable, "-m", "pytest", "tests/offline", "-q", "-p", "no:warnings", f"--junitxml={junit}"], cwd=ROOT
    )
    tree = ET.parse(junit).getroot()
    cases = list(tree.iter("testcase"))
    failures = [
        f"{c.get('classname')}::{c.get('name')}" for c in cases if c.find("failure") is not None or c.find("error") is not None
    ]
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    fixtures = hashlib.sha256((ROOT / "seed" / "expected" / "fixtures.json").read_bytes()).hexdigest()[:12]
    report = {
        "run_id": run_id,
        "mode": "offline",
        "environment": "test",
        "started_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "switch_server_version": os.environ.get("SWITCH_SERVER_VERSION", "n/a (offline: mocked bridge)"),
        "app_commit": commit,
        "fixture_version": fixtures,
        "assertions": {"tests": len(cases), "passed": len(cases) - len(failures), "failed": len(failures)},
        "failures": failures,
        "artifacts": [str(junit.relative_to(ROOT))],
    }
    body = json.dumps(report, sort_keys=True, indent=1)
    report["report_hash"] = hashlib.sha256(body.encode()).hexdigest()
    path = out / f"acceptance-{run_id}.json"
    path.write_text(json.dumps(report, sort_keys=True, indent=1), "utf-8")
    print(f"acceptance {run_id}: {report['assertions']} -> {path.relative_to(ROOT)}")
    return code


if __name__ == "__main__":
    sys.exit(main())
