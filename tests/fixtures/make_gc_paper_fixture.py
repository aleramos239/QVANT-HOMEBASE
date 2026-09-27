"""Regenerate the GC paper-runner parity fixtures from the tick archive — read-only.

    .venv/bin/python tests/fixtures/make_gc_paper_fixture.py

For each pinned event day (research window 2021-2024 only) it reads the front
contract's archive file from ~/futures_ticks (NEVER written), keeps the prints in
08:29:30 <= ts < 09:56:00 ET, and writes

  tests/fixtures/gc_paper_<date>.csv.gz   ts_ms,price,size,ts_ns (archive-readable, tape order)
  tests/fixtures/gc_paper_expected.json   run_session(GCNfpCpi(), FULL archive tape, Costs())'s
                                          trades + anchor per day, so the tests can check the
                                          trimmed tape trades exactly like the whole session.
"""
from __future__ import annotations

import csv
import datetime as dt
import gzip
import io
import json
import sys
from bisect import bisect_left
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent))

from homebase.backtest.engine import Costs, run_session  # noqa: E402
from homebase.backtest.tape import Tape, TapeStore, et_ns, read_archive_csv, stable_sorted  # noqa: E402
from homebase.strategies.gc_nfpcpi import GCNfpCpi, calendar  # noqa: E402

# (date, why) — pinned 2026-09-27
DAYS = [("2024-09-06", "NFP, stop-loss exit that gapped (net -434)"),
        ("2024-11-13", "CPI, take-profit exit (net +596)")]
FROM, TO = "08:29:30", "09:56"


def main() -> None:
    store = TapeStore()
    expected = {}
    for iso, why in DAYS:
        d = dt.date.fromisoformat(iso)
        assert d.year <= 2024 and calendar()[d] & {"NFP", "CPI"}, iso
        src, contract = store.pick("GC", d)
        ts, px, sz = stable_sorted(*read_archive_csv(src))
        res = run_session(GCNfpCpi(), Tape("GC", d, contract, ts, px, sz, {}), Costs())
        a, b = bisect_left(ts, et_ns(d, FROM)), bisect_left(ts, et_ns(d, TO))
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["ts_ms", "price", "size", "ts_ns"])
        for i in range(a, b):
            w.writerow([ts[i] // 1_000_000, repr(px[i]), sz[i], ts[i]])
        (HERE / f"gc_paper_{iso}.csv.gz").write_bytes(gzip.compress(buf.getvalue().encode(), 9))
        expected[iso] = {"why": why, "contract": contract, "source": src.name, "ticks": b - a,
                         "anchor": next(h["price"] for h in res.hlines if h["name"] == "anchor"),
                         "trades": [t.to_dict() for t in res.trades]}
        print(iso, contract, b - a, [(t.side, t.exit_reason, t.net) for t in res.trades])
    (HERE / "gc_paper_expected.json").write_text(json.dumps(expected, indent=1) + "\n")


if __name__ == "__main__":
    main()
