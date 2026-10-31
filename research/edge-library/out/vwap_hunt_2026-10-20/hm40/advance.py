"""Portfolio hunt: move every store one step along (PREREG_HM40.md sections 4-5, Amendments A-B). Run it as often as you like; it keeps its
state in advance_state.json and only adds lines to ../queue_hm.txt (the runner runs them).

  1. an idea is COMPLETE when every spec of it in specs/ has its in-sample store: only then is its average (C6) final;
  2. a store of a complete idea with chosen versions gets its worse-fills pass ("wfw <spec>", queue front);
  3. then THE PICK: the middle of its chosen versions by in-sample average trade whose worse-fills net (its group) is > 0 (the middle
     first, then outward); it is written to PICKS.md, then locked (`bp.py wf pick`), then its test months queued ("oos <store> <box>");
  4. after the test-month read: the random entries on the same months ("roos <store>", oosrand.py);
  5. then the grade (P1-P5, the in-sample C6), in GRADES.md, and the luck count in LUCK.md.
No test month is read to decide anything in steps 1-3; step 5 reads the picked box's test months only."""
from __future__ import annotations

import datetime as dt
import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import hmread as HR  # noqa: E402
import oosrand as OR  # noqa: E402

EL = HR.EL
PY = EL.parents[1] / ".venv-research" / "bin" / "python"
Q = HERE.parent / "queue_hm.txt"
STATE = HERE / "advance_state.json"
FRESH = ("2025-09", "2026-01", "2026-05")
WHO = "claude: the owner's standing word of 2026-10-20 (PREREG_HM40 s4 / Amendment B rule)"
BAR = "J"                                        # Amendment J: P1 = win rate >= break-even (the grade is redone when the bar changes)
PIN = "2026-05"                                  # the hunt's 14 blocks (the last test month), held for the whole hunt (review 2026-10-21)


def _now() -> str:
    return dt.datetime.now(HR.dt.timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M %Z")


def _queue(line: str, front: bool = True) -> None:
    lines = Q.read_text().splitlines()
    if line in lines:
        return
    head = [ln for ln in lines if ln.startswith("#")]
    body = [ln for ln in lines if ln.strip() and not ln.startswith("#")]
    Q.write_text("\n".join(head + ([line] + body if front else body + [line])) + "\n")


def _worse_by_group(home: Path, sessions: list) -> dict:
    """{(box, group): worse-fills net} from the store's worse-fills stores (one a session), or {} when any is missing."""
    out = defaultdict(float)
    for s in sessions:
        d = home / f"is-{s}-worse"
        if not (d / "cells.npz").exists():
            return {}
        w = HR.LB.load_unit(d.name, home)
        g = next(k for k, v in HR.GROUPS.items() if s in v)
        for i, c in enumerate(w["meta"]["cells"]):
            out[(c["id"], g)] += float(HR.LB.unit_cell(w, i)["net"].sum())
    return dict(out)


def _middle_out(n: int) -> list:
    m = (n - 1) // 2
    order, k = [m], 1
    while len(order) < n:
        for j in (m - k, m + k):                     # middle, then lower, then higher (pipe_stages._outward)
            if 0 <= j < n:
                order.append(j)
        k += 1
    return order


def grade(store: str, box: str, group: str, spec: dict, idea_avg: float) -> dict:
    home = HR.RUNS / store
    u = HR.LB.load_unit("oos", home)
    x = HR.LB.unit_cell(u, 0)
    m = u["meta"]
    if u["meta"]["cells"][0]["id"] != box:
        raise SystemExit(f"{store}: its test-month store holds {u['meta']['cells'][0]['id']}, not the picked {box}")
    codes = [HR.LB.SESS_CODE[s] for s in HR.GROUPS[group]]
    k = np.isin(x["sess"], codes)
    net = np.asarray(x["net"], np.float64)[k]
    mo = HR._months({"date": np.asarray(x["date"])[k]})
    ism = {d[:7] for d in HR.LB.load_unit("is", home)["meta"]["days"]}
    days = [d for bl in OR.WM.blocks(m["root"]) if set(bl["is"]) <= ism for d in OR.WM.oos_days(m["root"], bl["oos"])]   # the test sessions
    side = {"long": 1, "short": -1}.get((spec.get("limits") or {}).get("dir"))
    wr = HR.edge(net)
    r_both = OR.line(store, list(HR.GROUPS[group]))
    r_side = OR.line(store, list(HR.GROUPS[group]), side) if side else None
    fresh = net[np.isin(mo, FRESH)]
    t2 = HR.TICK2[m["root"]]
    g = {"store": store, "box": box, "group": group, "trades": int(len(net)), "per_day": round(len(net) / len(days), 3) if days else None,
         "net": round(float(net.sum()), 1), "avg": round(float(net.mean()), 2) if len(net) else None,
         "win": round(float((net > 0).mean()), 4) if len(net) else None, "need": wr.get("need"), "rr": wr.get("rr"),
         "be": wr.get("breakeven"), "margin": wr.get("margin"), "bar": BAR,
         "net_tick": round(float(net.sum()) - t2 * len(net), 1), "fresh_net": round(float(fresh.sum()), 1), "fresh_trades": int(len(fresh)),
         "rand": r_both, "rand_side": r_side, "months": {k2: round(float(net[mo == k2].sum())) for k2 in sorted(set(mo))}}
    b = {"P1": bool(len(net) and wr["passed"]), "P2": g["net"] > 0 and g["net_tick"] > 0,
         "P3": r_both == 1.0 and (r_side is None or r_side == 1.0), "P4": g["trades"] >= 100, "P5": g["fresh_trades"] > 0 and g["fresh_net"] > 0,
         "C6": idea_avg > 0}
    g["seen"] = HR.SEEN.get(int(spec["name"].split("_")[1][1:]))      # idea 1: its test months were read before (not fresh)
    g["bars"] = b
    g["passed"] = all(b.values())
    g["first_fail"] = next((k2 for k2, v in b.items() if not v), None)
    return g


def main() -> None:
    st = json.loads(STATE.read_text()) if STATE.exists() else {}
    specs = {p.stem: json.loads(p.read_text()) for p in sorted((HERE / "specs").glob("*.json"))}
    queued = {ln.split()[1] for ln in Q.read_text().splitlines() if ln.startswith("wfr ")}
    specs = {k: v for k, v in specs.items() if k in queued or HR.read_store(v)}          # the specs of this hunt that are queued or run
    rows, have = [], set()
    for n, sp in specs.items():
        r = HR.read_store(sp)
        if r:
            have.add(n)
            rows += r
    by_idea = defaultdict(list)
    for r in rows:
        if r.get("trades"):
            by_idea[r["idea"]].append(r["avg"])
    idea_avg = {i: float(np.mean(v)) for i, v in by_idea.items()}
    complete = {i for i in by_idea if all(n in have for n, sp in specs.items() if int(n.split("_")[1][1:]) == i)}
    for r in rows:
        r["chosen"], r["first_fail"] = HR.chosen(r, idea_avg)
    log = []
    for n, sp in specs.items():
        if n not in have:
            continue
        idea = int(n.split("_")[1][1:])
        store = f"{n}-{sp['markets'][0]}-tf{sp['bar_sizes'][0]}"
        home = HR.RUNS / store
        s = st.setdefault(store, {"stage": "new", "spec": n})
        if s["stage"] in ("none", "none_after_worse"):
            s["stage"] = "new"                       # Amendment J: looked at again on every pass (the bar can change what is chosen)
        if s["stage"] == "cap_wait":
            s["stage"] = "new"                       # the cap is read again on every pass
        if s["stage"] == "new":
            if idea not in complete:
                continue
            ch = sorted([r for r in rows if r["store"] == store and r["chosen"]], key=lambda r: (r["avg"], r["box"], r["group"]))
            if not ch:
                s["stage"] = "none"
                continue
            worse = _worse_by_group(home, sp["sessions"])
            if not worse:
                need = len(HR.LB.load_unit("is", home)["meta"]["cells"]) * len(sp["sessions"]) + 824 + 200
                if HR.LB.ledger_left()["cells"] < need:
                    s["stage"] = "cap_wait"
                    log.append(f"{store}: the ledger cap has {HR.LB.ledger_left()['cells']} cells left, {need} needed: waiting")
                    continue
                _queue(f"wfw {n}")
                s["stage"] = "worse_wait"
                log.append(f"{store}: {len(ch)} chosen; worse fills queued")
                continue
            s["stage"] = "worse_ready"
        if s["stage"] == "worse_wait":
            if _worse_by_group(home, sp["sessions"]):
                s["stage"] = "worse_ready"
        if s["stage"] == "worse_ready" and (HERE / "HOLD_PICKS").exists():
            log.append(f"{store}: pick held (HOLD_PICKS: the check-in; no new pick or test-month read)")
            continue
        if s["stage"] == "worse_ready":
            ch = sorted([r for r in rows if r["store"] == store and r["chosen"]], key=lambda r: (r["avg"], r["box"], r["group"]))
            worse = _worse_by_group(home, sp["sessions"])
            pick = next((ch[j] for j in _middle_out(len(ch)) if worse.get((ch[j]["box"], ch[j]["group"]), -1) > 0), None)
            if pick is None:
                s["stage"] = "none_after_worse"
                continue
            line = (f"| {_now()} | {store} | {pick['box']} | {pick['group']} | {len(ch)} | {pick['per_day']:.2f} | {pick['avg']:,.1f} | "
                    f"{pick['win'] * 100:.1f} % | {pick['need'] * 100:.1f} % | ${worse[(pick['box'], pick['group'])]:,.0f} | {idea_avg[idea]:,.1f} |")
            pf = HERE / "PICKS.md"
            if not pf.exists():
                pf.write_text("# Picks (written BEFORE each lock and test-month read; the middle of the chosen in-sample versions, worse fills > 0)\n\n"
                              "| Written | Store | Box | Group | Chosen | IS trades/day | IS avg $ | IS win | IS need | IS worse-fills net | Idea avg |\n"
                              "|---|---|---|---|---|---|---|---|---|---|---|\n")
            with open(pf, "a") as f:
                f.write(line + "\n")
            lf = home / "lock.json"
            if lf.exists() and json.loads(lf.read_text()).get("box") != pick["box"]:
                s.update(stage="locked_other", other=json.loads(lf.read_text()).get("box"))
                log.append(f"{store}: another box is locked already ({s['other']}): not read")
                continue
            out = subprocess.run([str(PY), "bp.py", "wf", "pick", store, pick["box"], f"--who={WHO}"], cwd=EL, capture_output=True, text=True,
                                 env={**__import__("os").environ, "HOMEBASE_WF_LAST": PIN})
            if out.returncode != 0:
                log.append(f"{store}: pick refused: {(out.stdout + out.stderr)[-300:]}")
                s["stage"] = "pick_error"
                continue
            s.update(stage="oos_wait", box=pick["box"], group=pick["group"])
            STATE.write_text(json.dumps(st, indent=1, default=str))
            _queue(f"oos {store} {pick['box']}")
            log.append(f"{store}: picked {pick['box']} ({pick['group']}); test months queued")
        if s["stage"] == "oos_wait" and (home / "oos" / "cells.npz").exists():
            _queue(f"roos {store}")
            s["stage"] = "rand_wait"
        elif s["stage"] == "oos_wait" and (EL / "out" / "vwap_hunt_2026-10-20" / "logs" / f"oos_{store}.failed").exists():
            from blueprint import reads as RD
            if RD.wf_oos_on_file(store, s["box"]):
                s["stage"] = "oos_used"               # claimed, then stopped: a used read, a fail
                log.append(f"{store}: its test-month read stopped after the claim: counted as read, fail")
        if s["stage"] == "rand_wait" and (home / "oos-rand.npz").exists():
            s["grade"] = grade(store, s["box"], s["group"], sp, idea_avg[idea])
            s["stage"] = "graded"
            log.append(f"{store}: graded -- {'PASS' if s['grade']['passed'] else 'fail ' + str(s['grade']['first_fail'])}")
        elif s["stage"] == "graded" and s["grade"].get("bar") != BAR:
            was = s["grade"]["passed"]
            s["grade"] = grade(store, s["box"], s["group"], sp, idea_avg[idea])
            log.append(f"{store}: re-graded on Amendment J -- {'PASS' if s['grade']['passed'] else 'fail ' + str(s['grade']['first_fail'])}"
                       f"{' (was a fail)' if s['grade']['passed'] and not was else ''}")
    STATE.write_text(json.dumps(st, indent=1, default=str))
    graded = [v["grade"] for v in st.values() if v.get("stage") == "graded"]
    L = ["# Grades of the picked boxes on their test months (PREREG_HM40.md section 5; Amendment A: P4 = 100 trades)", "",
         "Amendment J (the owner, 2026-10-21): P1 = win rate >= break-even of its realized reward-to-risk; Margin = win - break-even (points), "
         "+3 = the old bar.", "",
         "| Store | Box | Group | Trades | /day | Avg $ | Win | Break-even | Margin | +1 tick net | Fresh net (trades) | Random | Pass / first fail |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for g in graded:
        rs = "-" if g["rand"] is None else f"{g['rand']:.1f}" + ("" if g["rand_side"] is None else f" / side {g['rand_side']:.1f}")
        L.append(f"| {g['store']} | {g['box']} | {g['group']} | {g['trades']} | {g['per_day']} | {g['avg']} | {(g['win'] or 0) * 100:.1f} % | "
                 f"{(g.get('be') or 0) * 100:.1f} % | {g.get('margin') if g.get('margin') is not None else '-'}{' (+3)' if (g.get('margin') or 0) >= 3 else ''} | ${g['net_tick']:,.0f} | ${g['fresh_net']:,.0f} ({g['fresh_trades']}) | {rs} | "
                 f"{'PASS' if g['passed'] else g['first_fail']} |")
    (HERE / "GRADES.md").write_text("\n".join(L) + "\n")
    from blueprint import reads as RD
    n_read = sum(1 for k2, v in st.items() if v.get("stage") in ("oos_used", "rand_wait", "graded")
                 or (v.get("stage") == "oos_wait" and RD.wf_oos_on_file(k2, v.get("box"))))
    (HERE / "LUCK.md").write_text(f"# Luck count\n\nTest-month reads of this route (picked boxes, one a store): {n_read}. Passes: "
                                  f"{sum(g['passed'] for g in graded)} of {len(graded)} graded (Amendment J bar; "
                                  f"{sum(g['passed'] and (g.get('margin') or 0) >= 3 for g in graded)} of them also +3 points over break-even). Expected by luck on the random line alone: "
                                  f"{0.05 * n_read:.1f} (5 %). Updated {_now()}.\n")
    print("\n".join(log) or "nothing to move")
    print(f"ideas complete: {sorted(complete)}; stages: " + ", ".join(f"{k}: {v}" for k, v in sorted(defaultdict(int, {s2: sum(1 for v in st.values() if v['stage'] == s2) for s2 in {v['stage'] for v in st.values()}}).items())))


if __name__ == "__main__":
    main()
