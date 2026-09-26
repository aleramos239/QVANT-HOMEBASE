"""The chart page's pure JavaScript (indicator catalog, drawing geometry),
tested with Node's built-in runner. Skipped where Node is not installed."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

JS_TESTS = Path(__file__).parent / "js"


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_chart_page_javascript():
    files = sorted(str(p) for p in JS_TESTS.glob("*.test.mjs"))
    assert files, "no JS tests found"
    r = subprocess.run(["node", "--test", *files], capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, (r.stdout + r.stderr)[-6000:]
