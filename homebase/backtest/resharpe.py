"""One-off (owner, 2026-10-23): re-read the Sharpe and Sortino of every FINISHED saved tester result on the days that
traded only (report.py's rule since that day), from the trades each result already saved. Nothing is replayed.

Only Sharpe/Sortino keys move: every file is rebuilt, every other number the saved file holds must come back the same
(a key the code has added since, or a reworded label, is not written), and only its Sharpe/Sortino values are copied in;
a file where any other number differs is left alone (reported). Runs (tester runs, heat-map cells, walk-forward cells, test-month
reads): their report's Sharpe/Sortino fields only. Heat maps: each cell's summary Sharpe. Walk-forwards: months.json,
result.json and oos.json rebuilt the way the job built them, no look counted.

    python -m homebase.backtest.resharpe [BASE]           # a dry run: what would change
    python -m homebase.backtest.resharpe [BASE] --write   # write it (BASE: homebase/.state/tester)
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

from . import report
from . import walkforward as wf
from .runner import default_base, read_json, report_holes, write_json

MOVED = {"sharpe", "sortino", "sharpe_traded_days", "sharpe_basis"}


def _holds(old, new) -> bool:
    """Every number of `old` outside the Sharpe keys is in `new`, the same to 9 digits (another machine's last float digit
    differs), and keys only `new` has, and label text, are ignored."""
    if isinstance(old, dict):
        return isinstance(new, dict) and all(k in new and _holds(v, new[k]) for k, v in old.items() if k not in MOVED)
    if isinstance(old, list):
        return isinstance(new, list) and len(old) == len(new) and all(_holds(a, b) for a, b in zip(old, new))
    if isinstance(old, float) and isinstance(new, (int, float)) and not isinstance(new, bool):
        return math.isclose(old, new, rel_tol=1e-9, abs_tol=1e-9) or json.dumps(old) == json.dumps(new)    # NaN = NaN
    return isinstance(old, str) and isinstance(new, str) or json.dumps(old) == json.dumps(new)


def _merge(old, new):
    """`old` with each Sharpe key's value taken from `new` (a Sharpe key `new` no longer has is dropped)."""
    if isinstance(old, dict):
        return {k: (new[k] if k in MOVED else _merge(v, new[k])) for k, v in old.items() if k in new or k not in MOVED}
    if isinstance(old, list):
        return [_merge(a, b) for a, b in zip(old, new)]
    return old


def _ns(trades_ms: list[dict]) -> list[dict]:
    return sorted((wf.to_ns(t) for t in trades_ms), key=lambda t: (t["exit_ns"], t["entry_ns"]))


def new_run(run: dict, trades_ms: list[dict]) -> dict | None:
    """run.json with its report's Sharpe/Sortino re-read on traded days; None when it has no report or it is unchanged."""
    rep = run.get("report")
    if not isinstance(rep, dict) or "summary" not in rep:
        return None
    cov = run.get("coverage") or {}
    holes = rep.get("skipped") if "skipped" in rep else report_holes(cov.get("skipped") or [], cov.get("no_trade") or [])
    fresh = report.build(_ns(trades_ms), rep.get("capital", run.get("capital", 50_000.0)), skipped=holes)
    a, b = rep["summary"].get("all") or {}, fresh["summary"]["all"]
    if (a.get("trades"), a.get("net_profit")) != (b["trades"], b["net_profit"]):
        raise ValueError("its trades do not add up to its report")
    out = json.loads(json.dumps(rep, default=str))
    for side, col in out["summary"].items():
        col.pop("sharpe_traded_days", None)
        for k in ("sharpe", "sortino"):
            if k in col and side in fresh["summary"]:
                col[k] = fresh["summary"][side][k]
    for key in ("by_year", "by_month"):
        by = {p["period"]: p["sharpe"] for p in fresh.get(key, [])}
        for p in out.get(key) or []:
            if "sharpe" in p and p.get("period") in by:
                p["sharpe"] = by[p["period"]]
    out["sharpe_basis"] = fresh["sharpe_basis"]
    return None if out == rep else {**run, "report": out}


def _cell_months(d: Path, g: dict) -> list[str]:
    return (g.get("walkforward") or {}).get("months") or wf.month_list(wf.RESEARCH_START, wf.RESEARCH_END)


def new_wf(d: Path, g: dict) -> dict:
    """{file: new content} for a finished walk-forward's months.json / result*.json / compare.json, rebuilt as _stitch built them."""
    cfg, capital, out = g["walkforward"], g["capital"], {}
    ins = []
    for c in g["cells"]:
        cdir = d / "cells" / f"{c['i']:02d}"
        ms = wf.cell_months(cdir, _cell_months(d, g))
        out[cdir / "months.json"] = ms
        ins.append({"i": c["i"], "params": c["params"], "months": ms})

    def trades_of(i: int):
        cdir = d / "cells" / f"{i:02d}"
        return read_json(cdir / "trades.json") or [], wf._run_skipped(read_json(cdir / "run.json"))

    if cfg.get("scheme") == "fixed":
        out[d / "result.json"] = wf.fixed_result(ins, cfg, trades_of=trades_of, capital=capital)
    elif cfg.get("compare"):
        per, res = wf.compare_results(ins, cfg["months"], trades_of=trades_of, metric=cfg["metric"],
                                      min_trades=cfg["min_trades"], capital=capital, ratios=tuple(cfg.get("ratios") or wf.RATIOS))
        out.update({d / f"result-{n}.json": r for n, r in per.items()})
        out[d / "compare.json"] = res
    else:
        out[d / "result.json"] = wf.compute(ins, cfg["months"], trades_of=trades_of, metric=cfg["metric"],
                                            min_trades=cfg["min_trades"], capital=capital,
                                            test_months=cfg.get("test_months", wf.TEST_MONTHS),
                                            select_months=cfg.get("select_months", wf.SELECT_MONTHS),
                                            step_months=cfg.get("step_months"))
    return out


def new_oos(base: Path, d: Path, g: dict, got: dict) -> dict:
    """oos.json rebuilt from its test-month read's own cells (WalkForwardManager.oos_view's "done" branch)."""
    jd = base / wf._OosReads.SUBDIR / got["job"]
    st = read_json(jd / "grid.json")
    tr, sk = [], []
    for c in st["cells"]:
        cdir = jd / "cells" / f"{c['i']:02d}"
        tr += read_json(cdir / "trades.json") or []
        sk += wf._run_skipped(read_json(cdir / "run.json"))
    months = got["months"]
    return {**got, "record": wf.is_numbers(tr, sk, g.get("capital", 50_000.0), months),
            "blocks": [wf._block_row(b["i"], "oos", [m], tr) for b, m in zip(g["walkforward"]["blocks"], months)]}


def main(argv: list[str]) -> int:
    write = "--write" in argv
    args = [a for a in argv if a != "--write"]
    base = Path(args[0]) if args else default_base()
    tally = {"changed": 0, "same": 0, "skipped": []}
    runs: dict[Path, dict] = {}                  # run.json -> the run as it is after this pass (a dry run writes nothing)

    def put(path: Path, old, new) -> None:
        new = json.loads(json.dumps(new, default=str))
        if old is None or not _holds(old, new):
            tally["skipped"].append(f"{path}: more than its Sharpe would move")
            return
        new = _merge(old, new)
        if json.dumps(new) == json.dumps(old):
            tally["same"] += 1
        else:
            tally["changed"] += 1
            if write:
                write_json(path, new)

    for rj in sorted(base.rglob("run.json")):
        d = rj.parent
        try:
            run = read_json(rj)
            if not run or not run.get("finished") or not (d / "trades.json").exists():
                continue
            new = new_run(run, read_json(d / "trades.json") or [])
            if new is not None:
                put(rj, run, new)
            else:
                tally["same"] += 1
            runs[rj] = new or run
        except Exception as e:  # noqa: BLE001 -- one bad run never stops the rest
            tally["skipped"].append(f"{rj}: {type(e).__name__}: {e}")

    for gj in sorted((base / "grids").glob("*/grid.json")):
        try:
            g = read_json(gj)
            if g.get("status") != "done":
                continue
            new = json.loads(json.dumps(g))
            for c in new.get("cells", []):
                rep = (runs.get(gj.parent / "cells" / f"{c['i']:02d}" / "run.json") or {}).get("report") or {}
                if isinstance(c.get("summary"), dict) and "sharpe" in c["summary"] and rep:
                    c["summary"]["sharpe"] = rep["summary"]["all"]["sharpe"]
            put(gj, g, new)
        except Exception as e:  # noqa: BLE001
            tally["skipped"].append(f"{gj}: {type(e).__name__}: {e}")

    for gj in sorted((base / "walkforward").glob("*/grid.json")):
        d = gj.parent
        try:
            g = read_json(gj)
            if g.get("status") != "done":
                continue
            for path, new in new_wf(d, g).items():
                put(path, read_json(path), new)
            got = read_json(d / wf.OOS)
            if isinstance(got, dict) and got.get("state") == "done":
                put(d / wf.OOS, got, new_oos(base, d, g, got))
        except Exception as e:  # noqa: BLE001
            tally["skipped"].append(f"{d}: {type(e).__name__}: {e}")

    print(f"{'wrote' if write else 'would change'} {tally['changed']} files, {tally['same']} already right, "
          f"{len(tally['skipped'])} left alone")
    for s in tally["skipped"]:
        print("  left alone:", s)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
