"""pipe_view.py -- WHAT A PIPELINE IDEA DID, as a person looks at it: its equity curve and its executions on the chart
(2026-10-09, the owner: "cards in the book show results, metrics and a line equity curve ... open the chart from the book or
queue so I can see the executions").

READ-ONLY. Nothing is run and no test day is read again: both views read the trade list the pipeline itself stored for the idea's
PICKED box (the store's cells.npz), so they are the same trades its stages judged.

  curve(name, root)        `pipe curve <name>`: the picked box's trades by day -> the equity curve (cumulative net, one point a
                           traded day) and the numbers a person asks first (net, trades, win rate, average trade, profit factor,
                           worst day, deepest drawdown). A Book card reads its unseen test days; an idea still in the queue reads
                           the build days (what its stage 1 picked), once a pick is on file.
  executions(name, root)   `pipe executions <name>`: the same trades as a finished run of the tester (homebase/backtest/importrun.py,
                           the way the toolkit's own `show` does it), so Show-on-chart opens every entry and exit. A store keeps a
                           trade's time, net and stop distance, not its prices, so the prices are read here from the tape's
                           1-minute bars: the ENTRY is the open of the minute the engine filled in (its market entries go at the
                           next bar's open), the EXIT is that price plus the trade's own net in points -- the run's net stays the
                           engine's. A second call finds the run again and writes nothing new.

The picked box is the one `pipe show` names (state.picked: sub idea, bar, cell). Files read: <pipeline root>/book/<name>.json,
ideas/<name>/state.json, runs_test/<sub>-<MKT>-tf<bar>-<sess>-test/{run.json,cells.npz} (a Book card) or runs/<sub>-<MKT>-tf<bar>/
(a queued idea). Files written: executions.json beside the idea (the run id kept with the store's signature).
"""
from __future__ import annotations

import datetime as dt
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import judge as J
import l2sim as S
import numpy as np

from . import api
from . import pipe_store as PS

REASONS = ("sl", "tp", "time", "eod", "trail", "bars", "book", "other")
MIN_TRADES = 1


def _pick(name: str, root=None) -> tuple[dict, dict, dict]:
    """(state, card, picked) of an idea or a Book card; Refuse when it has nothing picked yet."""
    st = PS.state(name, root)
    picked = st.get("picked") or {}
    if not picked.get("sub") or not picked.get("cell"):
        raise J.Refuse(f"{name} has no picked box yet: its heat maps are judged at stage 1, and the executions are the picked box's trades")
    return st, PS.card(name, root), picked


def _store_dir(name: str, st: dict, card: dict, picked: dict, root=None) -> tuple[Path, str]:
    """(the store's folder, 'test' | 'build'): a Book card (or any idea that has its unseen-days store) reads the test days, else the build days."""
    market, bar, sess = str(card.get("market") or "").upper(), str(picked.get("bar") or card.get("bar") or ""), str(card.get("session") or "")
    sub = picked["sub"]
    test = PS._at(root) / "runs_test" / f"{sub}-{market}-tf{bar}-{sess}-test"     # read only: no folder is made, no pool linked
    if st.get("status") == "book" and (test / "cells.npz").is_file():
        return test, "test"
    build = PS._at(root) / "runs" / f"{sub}-{market}-tf{bar}"
    if (build / "cells.npz").is_file():
        return build, "build"
    raise J.Refuse(f"{name}: no stored trades for its picked box ({sub}) -- the store is written by stage 1")


def _trades(folder: Path, cell: str) -> tuple[dict, dict]:
    """(the run's meta, the picked cell's trade columns) from a store: cells.npz holds every cell's trades one after another, `off` marks where each starts."""
    meta = json.loads((folder / "run.json").read_text(encoding="utf-8"))
    ids = [c["id"] for c in meta.get("cells") or []]
    if cell not in ids:
        raise J.Refuse(f"the picked box {cell} is not a cell of {folder.name}")
    i = ids.index(cell)
    z = np.load(folder / "cells.npz")
    a, b = int(z["off"][i]), int(z["off"][i + 1])
    return meta, {k: z[k][a:b] for k in ("date", "entry_ms", "dur_s", "net", "side", "reason", "risk") if k in z.files}


def _dates(col) -> list:
    return [dt.date.fromordinal(int(x)).isoformat() for x in col]


def _numbers(net: np.ndarray, dates: list) -> dict:
    """The facts a person asks first, from the trade nets (dollars, one contract, after costs) and each trade's session date."""
    n = len(net)
    wins, losses = net[net > 0], net[net < 0]
    by_day: dict = {}
    for d, x in zip(dates, net.tolist()):
        by_day[d] = by_day.get(d, 0.0) + x
    days = sorted(by_day)
    cum, peak, dd, run = [], 0.0, 0.0, 0.0
    for d in days:
        run += by_day[d]
        peak = max(peak, run)
        dd = max(dd, peak - run)
        cum.append(round(run, 2))
    gain, loss = float(wins.sum()), -float(losses.sum())
    return {"trades": n, "days": len(days), "net": round(float(net.sum()), 2),
            "win_rate": round(len(wins) / n, 4) if n else None,
            "avg_trade": round(float(net.mean()), 2) if n else None,
            "avg_win": round(float(wins.mean()), 2) if len(wins) else None, "avg_loss": round(float(losses.mean()), 2) if len(losses) else None,
            "profit_factor": round(gain / loss, 3) if loss > 0 else None,
            "best_day": round(max(by_day.values()), 2) if by_day else None, "worst_day": round(min(by_day.values()), 2) if by_day else None,
            "max_drawdown": round(dd, 2), "curve": [[d, round(by_day[d], 2), c] for d, c in zip(days, cum)]}


def curve(name: str, root=None) -> dict:
    """`pipe curve <name>` -> {period, start, end, cell, market, session, trades, days, net, win_rate, avg_trade, profit_factor, worst_day,
    max_drawdown, curve: [[date, the day's net, cumulative net], ...]}."""
    st, card, picked = _pick(name, root)
    folder, period = _store_dir(name, st, card, picked, root)
    meta, x = _trades(folder, picked["cell"])
    if len(x["net"]) < MIN_TRADES:
        raise J.Refuse(f"{name}: the picked box has no trades in {folder.name}")
    dates = _dates(x["date"])
    out = _numbers(x["net"].astype(float), dates)
    return api.result("pipe curve", name, period=period, cell=picked["cell"], idea=picked["sub"], market=card.get("market"),
                      session=card.get("session"), bar=picked.get("bar") or card.get("bar"), start=dates[0] if dates else None,
                      end=dates[-1] if dates else None, side=card.get("sides"), text=f"{name}: {out['trades']} trades on {out['days']} days, net ${out['net']:,.0f}",
                      **out)


# ------------------------------------------------------------------------------------------------- executions

def _signature(folder: Path, cell: str) -> str:
    meta = json.loads((folder / "run.json").read_text(encoding="utf-8"))
    return f"{folder.name}|{cell}|{meta.get('inputs_hash') or ''}|{(folder / 'cells.npz').stat().st_size}"


def executions(name: str, root=None, tester=None) -> dict:
    """`pipe executions <name>` -> {run_id, trades, start, end, period, cell, fresh}: the picked box's trades as a finished run of the
    tester page (importrun), written once per store; a second call answers the same run id."""
    st, card, picked = _pick(name, root)
    folder, period = _store_dir(name, st, card, picked, root)
    meta, x = _trades(folder, picked["cell"])
    if not len(x["net"]):
        raise J.Refuse(f"{name}: the picked box has no trades in {folder.name}")
    sig = _signature(folder, picked["cell"])
    kept = PS._json(PS._dir(name, root) / "executions.json") or {}
    run_dir = (Path(tester) if tester else _tester_base()) / "runs" / str(kept.get("run_id") or "-")
    if kept.get("sig") == sig and (run_dir / "run.json").is_file():
        return api.result("pipe executions", name, run_id=kept["run_id"], trades=kept.get("trades"), start=kept.get("start"),
                          end=kept.get("end"), period=period, cell=picked["cell"], fresh=False,
                          text=f"{name}: {kept.get('trades')} executions, already on the tester page")
    market = str(card.get("market") or "").upper()
    dd = _dates(x["date"])
    dates = sorted(set(dd))
    start, end = dates[0], dates[-1]
    trades = [{"date": dd[i], "entry_ms": int(x["entry_ms"][i]), "dur_s": int(x["dur_s"][i]), "side": int(x["side"][i]), "net": float(x["net"][i]),
               "reason": REASONS[int(x["reason"][i])] if 0 <= int(x["reason"][i]) < len(REASONS) else "other"} for i in range(len(dd))]
    note = (f"pipeline idea {name} ({picked['sub']}), box {picked['cell']}: its {period} days; entries are the open of the filled "
            f"minute and exits follow the trade's own net (1 contract after costs)")
    title = f"{name}: {picked['cell']} ({market} {card.get('session')} {picked.get('bar') or card.get('bar')}m, {period} days)"
    with tempfile.TemporaryDirectory(prefix="pipe_exec_") as tmp:
        f = Path(tmp) / "trades.json"
        f.write_text(json.dumps({"trades": trades}))
        argv = [str(S.REPO / ".venv" / "bin" / "python"), "-B", "-m", "homebase.backtest.execrun", str(f), "--strategy", f"pipe_{name}"[:80],
                "--root", market, "--name", title[:80], "--start", start, "--end", end, "--sessions", str(len(dates)), "--note", note,
                *(["--base", str(tester)] if tester else [])]
        p = subprocess.run(argv, cwd=str(S.REPO), capture_output=True, text=True, timeout=600, stdin=subprocess.DEVNULL)
    if p.returncode != 0 or not p.stdout.strip():
        raise J.Refuse(f"execrun answered {p.returncode}: {(p.stderr or p.stdout).strip()[-300:] or 'nothing'}")
    got = json.loads(p.stdout.strip().splitlines()[-1])
    run_id = got["run_id"]
    PS._write(PS._dir(name, root) / "executions.json",
              {"run_id": run_id, "sig": sig, "trades": got["priced"], "start": start, "end": end, "period": period, "cell": picked["cell"]})
    return api.result("pipe executions", name, run_id=run_id, trades=got["priced"], of=got["of"], start=start, end=end, period=period,
                      cell=picked["cell"], fresh=True, text=f"{name}: {got['priced']} of {got['of']} executions written as run {run_id}")


def _tester_base() -> Path:
    sys.dont_write_bytecode = True
    repo = str(S.REPO)
    if repo not in sys.path:
        sys.path.append(repo)
    from homebase.backtest.runner import default_base
    return Path(default_base())
