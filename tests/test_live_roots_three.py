"""2026-10-27 (owner): the live feed, the tick job, the tape warm-up and the burst detector cover NQ, ES
and GC only. YM, RTY and SI history stays on disk and in the data export; their contract specs stay."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
THREE = ("NQ", "ES", "GC")
DROPPED = ("YM", "RTY", "SI")


def test_every_live_list_is_nq_es_gc():
    from homebase.backtest import tape
    from homebase.charts import DEFAULT_ROOTS, bursts
    from homebase.data import ticks
    assert DEFAULT_ROOTS == THREE and ticks.ROOTS == THREE and tape.WARM == THREE
    assert bursts.DEFAULT_ROOTS == THREE


def test_the_history_export_still_reads_the_old_archive():
    from homebase.charts import export
    assert set(DROPPED) <= set(export.ROOTS)          # reading a past day costs nothing live


def test_contract_specs_stay_for_the_old_markets():
    from homebase import contracts
    for r in DROPPED:
        assert r in contracts._SPECS, r


def test_charts_page_scripts_follow():
    app = (ROOT / "homebase/static/charts/app.js").read_text()
    start = re.search(r"const START = (\[.*?\]);", app, re.S).group(1)
    for r in DROPPED:
        assert f"'{r}'" not in start, r                # a fresh Charts opens no chart on a market with no feed
    bolt = re.search(r"const BOLT_ROOTS = \[(.*?)\]", (ROOT / "homebase/static/charts/indstatus.js").read_text()).group(1)
    assert re.findall(r"'(\w+)'", bolt) == list(THREE)
