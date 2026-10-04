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


def test_no_test_file_sits_in_the_served_static_folder():
    """A *.test.js under homebase/static is served to the browser and never run by the test above
    (algo-visibility's was there until 2026-10-04): every JS test lives in tests/js."""
    static = Path(__file__).parent.parent / "homebase" / "static"
    assert [str(p) for p in static.rglob("*.test.*")] == []
    assert (JS_TESTS / "algo-visibility.test.mjs").is_file()
