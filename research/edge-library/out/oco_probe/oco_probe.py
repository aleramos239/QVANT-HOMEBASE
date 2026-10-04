"""OCO CANCEL-DELAY PROBE (information only; no admission verdict is changed, nothing is booked as a candidate cell).
The engine cancels the other leg of an OCO bracket ON the fill print. Live, the cancel takes time: in a news burst both
legs can fill. Costs.oco_cancel_ms = D keeps the other leg working D ms after the first fill; a trigger inside the window
is a DOUBLE FILL = a second, independent position with its own stop and target (trade rows tagged double_fill 1 / 2).
The CENTRAL cell of each of the four members, BUILD (2021-09-22..2023-12-31) and 2024, D = 0 / 25 / 50 / 100 / 250 ms.
Event members run on their release days only (out/events/ev.py groups A / B / C). EXAM (2025+) is never named.
  python out/oco_probe/oco_probe.py run     the 40 runs (restartable: out/oco_probe/runs/), ledger rows stage `member`, kind `run`
  python out/oco_probe/oco_probe.py gaps    the distance between the two entry orders (0 ms cell, Ctx.oco watched in-process)
  python out/oco_probe/oco_probe.py report  -> oco_probe.json, double_fills.csv, tables on stdout
Every 2024 read is appended to out/oco_probe/pick_reads.csv BEFORE it runs."""
import csv
import datetime as dt
import json
import sys
from multiprocessing import get_context
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
W = HERE.parents[1]
for p in (str(W), str(W / "engine"), str(W / "out" / "events")):
    if p not in sys.path:
        sys.path.insert(0, p)
import ev as E  # noqa: E402
import families as F  # noqa: E402
import l2sim as S  # noqa: E402
import library as LB  # noqa: E402
import run_menus as RM  # noqa: E402

DELAYS = (0, 25, 50, 100, 250)
PERIODS = ("build", "pick")
MEMBERS = (("orb_NQ_tf1_pre", None), ("straddle_tight_0830_GC_tf30_pre_evA", "A"),
           ("straddle_tight_0830_NQ_tf30_pre_evB", "B"), ("straddle_tight_1000_GC_tf30_nyam_evC", "C"))
RUNS = HERE / "runs"
READS = HERE / "pick_reads.csv"
SEAL = "2025-01-01"


def member(name: str) -> dict:
    spec = json.loads((W / "members" / name / "spec.json").read_text())
    assert spec["admit"] and spec["plateau"]["build"]["pass"] is True          # 2024 is read for BUILD survivors only
    cls = F.REGISTRY[spec["family"]][0]
    params = dict(spec["inputs"])
    timed = "shift_seed" in cls.defaults()
    return {"name": name, "spec": spec, "cls": cls, "params": params, "root": spec["root"], "tf": spec["tf"],
            "family": spec["family"], "cell": spec["cell"], "timed": timed, "sess": spec["sess"], "group": dict(MEMBERS)[name],
            "feats": F.features_for(spec["family"], S.template_feature_needs(params)),
            "kw": dict(getattr(cls, "SCREEN_RUN", {}))}


def days_of(m: dict, per: str) -> list:
    """The sessions the member trades in the period: its release days (event members), every session (orb)."""
    a, b = S.period(per)
    assert b.isoformat() < SEAL
    if m["group"] is None:
        return [d.isoformat() for d in S.sessions(a, b, m["root"])]
    return sorted(d for d in E.days(m["group"]) if a.isoformat() <= d <= b.isoformat())


def own(m: dict, trades: list) -> list:
    tr = trades if m["timed"] else [t for t in trades if S.session_of(t["entry_ms"]) == m["sess"]]
    assert all(t["date"] < SEAL for t in tr)
    return tr


def log_read(m: dict, key: str, what: str) -> None:
    new = not READS.exists()
    with READS.open("a", newline="") as fh:
        w = csv.writer(fh)
        if new:
            w.writerow(["utc", "key", "family", "root", "tf", "sess", "what", "cells", "why"])
        w.writerow([dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), key, m["family"], m["root"], m["tf"], m["sess"],
                    what, 1, "OCO cancel-delay robustness probe of an admitted member's central cell (2024 already read for this cell)"])


def run_one(m: dict, per: str, ms: int) -> dict:
    key = f"{m['name']}-{m['cell']}-{per}-oco{ms}"
    p = RUNS / f"{key}.json"
    if p.exists():
        return json.loads(p.read_text())
    if per == "pick":
        log_read(m, key, f"central cell, oco_cancel_ms = {ms}")
    S.wait_compute_window()
    span = {"period": per} if m["group"] is None else {"days": days_of(m, per)}
    res = S.run(m["cls"], m["params"], root=m["root"], features=m["feats"], workers=RM.auto_workers(),
                costs=S.Costs(oco_cancel_ms=ms), **span, **m["kw"])
    out = {"key": key, "ms": ms, "period": per, "trades": own(m, res["trades"]), "sessions": res["sessions"],
           "skipped_by_error": res["skipped_by_error"], "elapsed_s": res["elapsed_s"], "stress": res["meta"]["stress"]}
    RUNS.mkdir(exist_ok=True)
    p.write_text(json.dumps(out, separators=(",", ":")))
    LB.ledger_add("member", key, "run", family=m["family"], root=m["root"], tf=str(m["tf"]), period=per, control=f"oco{ms}ms",
                  trades=len(out["trades"]), elapsed_s=res["elapsed_s"],
                  note="OCO cancel-delay robustness probe (information only; a re-run of a member cell)")
    return out


def cmd_run() -> None:
    for name, _ in MEMBERS:
        m = member(name)
        for per in PERIODS:
            stored = json.loads((W / "members" / name / f"trades_{per}.json").read_text())
            for ms in DELAYS:
                r = run_one(m, per, ms)
                tr = r["trades"]
                n2 = sum(1 for t in tr if t.get("double_fill") == 2)
                print(f"{name} {per} {ms:>3} ms: {len(tr)} entries, {n2} double fills, net {sum(t['net'] for t in tr):,.0f}, "
                      f"dropped sessions {r['skipped_by_error']}, {r['elapsed_s']} s", flush=True)
                assert r["skipped_by_error"] == 0, "a session was dropped by a strategy error"
                if ms == 0:                                       # the default is the law: the stored member rows, field by field
                    assert len(tr) == len(stored) and [{k: t[k] for k in s} for t, s in zip(tr, stored)] == stored, (name, per)
                    assert not any("double_fill" in t for t in tr) and r["stress"] is None


# ---- the distance between the two entry orders -------------------------------------------------------------
def gap_chunk(args) -> tuple:
    name, days = args
    m = member(name)
    seen = []
    orig = S.Ctx.oco

    def oco(self, *orders):
        orig(self, *orders)
        if len(orders) == 2 and orders[0].side != orders[1].side:
            seen.append((str(self.date), float(orders[0].price), float(orders[1].price)))
    S.Ctx.oco = oco
    try:
        res = S.run(m["cls"], m["params"], days=days, root=m["root"], features=m["feats"], workers=1, keep_ns=True, **m["kw"])
    finally:
        S.Ctx.oco = orig
    tr = own(m, res["trades"])
    # OWN RECOUNT on the tape (no engine order code): after the first leg's trigger print, does a print inside D ms reach
    # the other entry order? Must equal the engine's double-fill count at every delay.
    hits = {ms: 0 for ms in DELAYS[1:]}
    for t in tr:
        op, sd = float(t["order_price"]), (1 if t["side"] == "long" else -1)
        sib = [b if abs(a - op) < 1e-9 else a for d, a, b in seen if d == t["date"] and min(abs(a - op), abs(b - op)) < 1e-9]
        if not sib:
            continue
        tape = S.load_tape(dt.date.fromisoformat(t["date"]), m["root"])
        ts, px = tape.ts, tape.px
        a, b = int(np.searchsorted(ts, t["entry_ns"], "left")), int(np.searchsorted(ts, t["entry_ns"], "right"))
        k = next(i for i in range(a, b) if sd * (px[i] - op) >= -1e-9)
        for ms in hits:
            seg = px[k:int(np.searchsorted(ts, int(ts[k]) + ms * 1_000_000, "left"))]
            hits[ms] += bool((seg <= sib[0] + 1e-9).any() if sd > 0 else (seg >= sib[0] - 1e-9).any())
    return seen, [{k: v for k, v in t.items() if k not in ("entry_ns", "exit_ns")} for t in tr], hits


def cmd_gaps() -> None:
    out = {}
    n = RM.auto_workers()
    with get_context("spawn").Pool(n) as pool:
        for name, _ in MEMBERS:
            m = member(name)
            pv = S.SPECS[m["root"]][0]
            rows, base, recount = [], [], {}
            for per in PERIODS:
                days = days_of(m, per)
                if per == "pick":
                    log_read(m, f"{name}-{m['cell']}-pick-gaps", "central cell at 0 ms, entry-order prices watched (no new cell)")
                S.wait_compute_window()
                k = max(1, min(len(days), n * 4))
                tr, hits = [], {ms: 0 for ms in DELAYS[1:]}
                for seen, t, h in pool.imap_unordered(gap_chunk, [(name, days[i::k]) for i in range(k)]):
                    rows += [(per,) + s for s in seen]
                    tr += t
                    hits = {ms: hits[ms] + h[ms] for ms in hits}
                eng = {ms: sum(1 for t in json.loads((RUNS / f"{name}-{m['cell']}-{per}-oco{ms}.json").read_text())["trades"]
                               if t.get("double_fill") == 2) for ms in hits}
                recount[per] = {"tape": hits, "engine": eng, "equal": hits == eng}
                tr.sort(key=lambda t: t["entry_ms"])
                ref = json.loads((HERE / "runs" / f"{name}-{m['cell']}-{per}-oco0.json").read_text())["trades"]
                assert [(t["entry_ms"], t["net"]) for t in tr] == [(t["entry_ms"], t["net"]) for t in ref], (name, per)
                base += tr
            filled = {(t["date"], round(float(t["order_price"]), 6)) for t in base}
            g_all = np.array([abs(a - b) for _, _, a, b in rows])
            g = np.array([abs(a - b) for _, d, a, b in rows if (d, round(a, 6)) in filled or (d, round(b, 6)) in filled])
            q = lambda x, v: round(float(np.percentile(x, v)), 4)  # noqa: E731
            out[name] = {"root": m["root"], "point_value": pv, "brackets": int(len(g_all)), "brackets_filled": int(len(g)),
                         "recount": recount,
                         "pts": {"p10": q(g, 10), "median": q(g, 50), "p90": q(g, 90), "min": q(g, 0)},
                         "usd": {"p10": round(q(g, 10) * pv, 2), "median": round(q(g, 50) * pv, 2), "p90": round(q(g, 90) * pv, 2)}}
            print(name, json.dumps(out[name]), flush=True)
    (HERE / "gaps.json").write_text(json.dumps(out, indent=1))


# ---- the report ------------------------------------------------------------------------------------------------
def pairs(trades: list) -> list:
    """[(first leg, late leg)] of every double fill: per date, the row tagged 1 with the row tagged 2 that follows it."""
    out, first = [], {}
    for t in sorted((t for t in trades if t.get("double_fill")), key=lambda t: t["entry_ms"]):
        if t["double_fill"] == 1:
            assert t["date"] not in first
            first[t["date"]] = t
        else:
            out.append((first.pop(t["date"]), t))
    assert not first
    return out


def cmd_report() -> None:
    rep, rows = {}, []
    for name, _ in MEMBERS:
        m = member(name)
        rep[name] = {"root": m["root"], "cell": m["cell"], "point_value": S.SPECS[m["root"]][0]}
        for per in PERIODS:
            base = None
            for ms in DELAYS:
                r = json.loads((RUNS / f"{name}-{m['cell']}-{per}-oco{ms}.json").read_text())
                tr = r["trades"]
                net = round(sum(t["net"] for t in tr), 2)
                base = net if ms == 0 else base
                pp = pairs(tr)
                pn = [round(a["net"] + b["net"], 2) for a, b in pp]
                rep[name][f"{per}|{ms}"] = {
                    "entries": len(tr), "double_fills": len(pp), "share_of_filled_brackets": round(len(pp) / max(1, len(tr) - len(pp)), 4),
                    "pair_net": round(sum(pn), 2), "late_leg_net": round(sum(b["net"] for _, b in pp), 2), "net": net,
                    "delta_vs_0ms": round(net - base, 2), "worst_pair": min(pn) if pn else None,
                    "pairs_losing": sum(1 for v in pn if v < 0), "dropped_sessions": r["skipped_by_error"]}
                for a, b in pp:
                    rows.append([name, per, ms, a["date"], a["side"], a["entry_ms"], b["entry_ms"] - a["entry_ms"], a["entry_price"],
                                 b["entry_price"], a["exit_reason"], b["exit_reason"], a["net"], b["net"], round(a["net"] + b["net"], 2)])
    gp = HERE / "gaps.json"
    if gp.exists():
        for name, g in json.loads(gp.read_text()).items():
            rep[name]["order_gap"] = g
    (HERE / "oco_probe.json").write_text(json.dumps(rep, indent=1))
    with (HERE / "double_fills.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["member", "period", "oco_cancel_ms", "date", "first_side", "first_entry_ms", "lag_ms", "first_entry", "late_entry",
                    "first_exit", "late_exit", "first_net", "late_net", "pair_net"])
        w.writerows(rows)
    for name, _ in MEMBERS:
        print(f"\n{name}  gap {json.dumps(rep[name].get('order_gap', {}).get('pts'))} pts {json.dumps(rep[name].get('order_gap', {}).get('usd'))} $")
        print("  ms | BUILD entries dbl share pair_net net delta worst | 2024 entries dbl share pair_net net delta worst")
        for ms in DELAYS:
            b, k = rep[name][f"build|{ms}"], rep[name][f"pick|{ms}"]
            f = lambda x: (f"{x['entries']:>4} {x['double_fills']:>3} {100 * x['share_of_filled_brackets']:>5.1f}% {x['pair_net']:>8,.0f} "  # noqa: E731
                           f"{x['net']:>8,.0f} {x['delta_vs_0ms']:>8,.0f} {x['worst_pair'] if x['worst_pair'] is not None else '-':>7}")
            print(f"  {ms:>3} | {f(b)} | {f(k)}")


if __name__ == "__main__":
    {"run": cmd_run, "gaps": cmd_gaps, "report": cmd_report}[sys.argv[1]]()
