#!/usr/bin/env python3
"""Daily shadow report: the stack (nq_sk_*, 8 rules / 20 drafts, from 2026-10-22; STACK_BAR.md) and the 3 earlier rules
(nq_vh_*, from 2026-10-22; SHADOW_BAR.md) -> STACK_REPORT.md next to this file.

Reads only ~/.homebase/desklab/<draft>/days/<YYYY-MM-DD>.json (what the Desk runner writes). Writes only STACK_REPORT.md.
    python stack_report.py              # the report
    python stack_report.py --selftest   # fake day files in a temp dir, assert-based
"""
import datetime as dt
import json
import math
import sys
import tempfile
from pathlib import Path

import numpy as np

DESKLAB = Path.home() / ".homebase" / "desklab"
OUT = Path(__file__).with_name("STACK_REPORT.md")
SESSIONS = ("nyam", "mid", "pm")
STACK, VH = ("nq_sk_", "2026-10-22"), ("nq_vh_", "2026-10-22")      # (draft prefix, first counted date)
SB = ("nq_sb_", "2026-10-23")                                        # stack B (Amendment L): day 1 = the first session all 4 drafts are on (the 3 touch drafts start the evening before: on at 22:09 on 10-21 was too late for 10-22)
# vh 10-21 = catch-up replays (rebuilt, promoted 14:38 / 17:22 ET, VPS only): not counted, as STACK_BAR 1 and SHADOW_BAR ("expected 10-22")
READ_DATE = dt.date(2027, 4, 22)                                     # STACK_BAR 1: the one read
STOP_FROM, STOP_T, FIDELITY = 100, -2.0, 0.90                        # STACK_BAR 3 and 2
VH_BAR = {"adxtouch": ("VWAP touch, ADX days", 80, 1576),          # SHADOW_BAR 2: test-month avg and sd a trade;
          "emavwap": ("EMA x VWAP + RVOL", 74, 1645),                # stop when avg < avg - 2 sd / sqrt(n), from 30 trades
          "rvbrk": ("RVOL break 5m", 43, 1676)}
VH_STOP_FROM = 30


TAGS = Path(__file__).with_name("day_tags.json")                 # {date: true (middle day) / false / null}: read once from the day's prints
REPO = Path(__file__).resolve().parents[5]


def day_tag(date):
    """Amendment M: True = a MIDDLE day (the 09:30 open in the middle third of the 01:00-09:30 ET range of the day's own prints),
    False = not, None = no prints on file yet. Remembered in day_tags.json."""
    tags = json.loads(TAGS.read_text()) if TAGS.exists() else {}
    if date in tags and tags[date] is not None:
        return tags[date]
    try:
        sys.path.insert(0, str(REPO))
        from homebase.backtest.tape import TapeStore, et_ns
        d = dt.date.fromisoformat(date)
        tape = TapeStore().load("NQ", d)
        out = None
        if tape is not None and len(tape.ts):
            ts, px = np.asarray(tape.ts), np.asarray(tape.px, float)
            a, b, c = et_ns(d, "01:00"), et_ns(d, "09:30"), et_ns(d, "09:35")
            rng = px[(ts >= a) & (ts < b)]
            op = px[(ts >= b) & (ts < c)]
            if len(rng) and len(op) and rng.max() > rng.min():
                th = (rng.max() - rng.min()) / 3
                out = bool(rng.min() + th <= op[0] <= rng.min() + 2 * th)
            elif len(rng) and len(op):
                out = False
    except Exception:                                   # noqa: BLE001 - no tape, no tag; the report must still come out
        out = None
    tags[date] = out
    TAGS.write_text(json.dumps(tags, indent=0, sort_keys=True))
    return out


TAGGER = day_tag

FLAT = Path(__file__).with_name("day_tags_flat.json")             # {date: true (flat open) / false / null}
GAP_CUTS = (-0.105, 0.163)                                       # Note N, frozen from the in-sample days: gap/20-day range; flat = above the first, up to the second


def flat_tag(date):
    """Note N: True = a FLAT-OPEN day (the 09:30 open minus the prior 16:00 close, over the mean range of the 20 prior sessions, inside the
    frozen cut points), False = not, None = a number is missing. Read from the tape store; remembered in day_tags_flat.json."""
    tags = json.loads(FLAT.read_text()) if FLAT.exists() else {}
    if date in tags and tags[date] is not None:
        return tags[date]
    out = None
    try:
        sys.path.insert(0, str(REPO))
        from homebase.backtest.tape import TapeStore, et_ns
        d, store = dt.date.fromisoformat(date), TapeStore()
        tape = store.load("NQ", d)
        ts, px = np.asarray(tape.ts), np.asarray(tape.px, float)
        op = px[(ts >= et_ns(d, "09:30")) & (ts < et_ns(d, "09:35"))]
        rngs, prev_close, k = [], None, d
        for _ in range(45):                                        # back over calendar days until 20 sessions and the prior close are found
            k -= dt.timedelta(days=1)
            if len(rngs) >= 20 and prev_close is not None:
                break
            dly = store.daily("NQ", k)
            if dly is None:
                continue
            if len(rngs) < 20:
                rngs.append(float(dly["h"]) - float(dly["l"]))
            if prev_close is None:
                t = store.load("NQ", k)
                tt, pp = np.asarray(t.ts), np.asarray(t.px, float)
                m = (tt >= et_ns(k, "15:30")) & (tt < et_ns(k, "16:00"))
                prev_close = float(pp[m][-1]) if m.any() else None
        if len(op) and len(rngs) == 20 and prev_close is not None and np.mean(rngs) > 0:
            gap = (float(op[0]) - prev_close) / float(np.mean(rngs))
            out = bool(GAP_CUTS[0] < gap <= GAP_CUTS[1])
    except Exception:                                   # noqa: BLE001 - no tape, no tag; the report must still come out
        out = None
    tags[date] = out
    FLAT.write_text(json.dumps(tags, indent=0, sort_keys=True))
    return out


FLAT_TAGGER = flat_tag


def load(root, prefix, start):
    """{draft: {date: day}} for every draft folder named prefix*; counted dates >= start, plus how many earlier files were left out."""
    drafts, early = {}, 0
    for days_dir in sorted(Path(root).glob(prefix + "*/days")):
        days = {}
        for f in sorted(days_dir.glob("*.json")):
            if f.stem < start:
                early += 1
                continue
            try:
                days[f.stem] = json.loads(f.read_text())
            except (OSError, ValueError) as e:                       # a half-written file must not hide the rest
                days[f.stem] = {"state": "unreadable", "why": str(e)[:80], "trades": []}
        drafts[days_dir.parent.name] = days
    return drafts, early


def rule_of(name, prefix):
    head, _, tail = name[len(prefix):].rpartition("_")
    return head if tail in SESSIONS else name[len(prefix):]


def rows_of(drafts, prefix):
    return [(date, name, rule_of(name, prefix), day) for name, days in drafts.items() for date, day in days.items()]


def stats(nets):
    """Trades -> n, net, avg, win (net > 0), break-even of the realized reward-to-risk (avg loss / (avg win + avg loss)), se, t."""
    a = np.asarray(nets, float)
    s = {"n": int(a.size), "net": float(a.sum()), "avg": None, "win": None, "be": None, "se": None, "t": None}
    if a.size:
        s["avg"], s["win"] = float(a.mean()), float((a > 0).mean())
        w, l = a[a > 0], -a[a < 0]
        if w.size and l.size:
            s["be"] = float(l.mean() / (w.mean() + l.mean()))
        if a.size > 1 and a.std(ddof=1) > 0:
            s["se"] = float(a.std(ddof=1) / math.sqrt(a.size))
            s["t"] = s["avg"] / s["se"]
    return s


def block(rows):
    """Numbers of a set of draft-days. A day counts once any draft has started it (state past 'waiting'). Fidelity = done
    draft-days whose match.ok is true / done draft-days whose match has run (pending matches, running, waiting, stopped, off,
    not-today days left out)."""
    s = stats([float(t.get("net") or 0) for *_, d in rows for t in d.get("trades") or []])
    done = [d for *_, d in rows if d.get("state") == "done"]
    oks = [(d.get("match") or {}).get("ok") for d in done]
    days = {date for date, *_, d in rows if d.get("state") != "waiting"}
    s.update(days=len(days), drafts=len({r[1] for r in rows}), done=len(done), ok=oks.count(True), bad=oks.count(False),
             fid=oks.count(True) / (oks.count(True) + oks.count(False)) if oks.count(True) + oks.count(False) else None, per_day=s["n"] / len(days) if days else None)
    return s


def money(x):
    return "-" if x is None else f"{x:+,.0f}"


def pct(x):
    return "-" if x is None else f"{x * 100:.1f} %"


def num(x):
    return "-" if x is None else f"{x:+.2f}"


HEAD = "| Days | Trades | Trades a day | Net $ | Avg trade $ | Win | Break-even | t of avg | Fidelity |\n|---|---|---|---|---|---|---|---|---|"


def cells(s):
    per_day = "-" if s["per_day"] is None else f"{s['per_day']:.2f}"
    fid = "-" if s["fid"] is None else f"{pct(s['fid'])} ({s['ok']}/{s['ok'] + s['bad']})"
    return (f"{s['days']} | {s['n']} | {per_day} | {money(s['net'])} | {money(s['avg'])} | {pct(s['win'])} | {pct(s['be'])} | "
            f"{num(s['t'])} | {fid}")


def stack_stop(s, check_day=True):
    """STACK_BAR 3: from 100 stack trades, t <= -2 -> STOP -- read only on the month's first stack session (check_day)."""
    if s["n"] < STOP_FROM:
        return f"not checked yet: {s['n']} of {STOP_FROM} trades"
    if not check_day:
        return f"not a check day (only the month's first session counts); t now {num(s['t'])}"
    if s["t"] is not None and s["t"] <= STOP_T:
        return f"**STOP** -- t = {s['t']:+.2f} <= {STOP_T:+.0f} at {s['n']} trades: the bar says switch the stack off, failed"
    line = STOP_T * s["se"] if s["se"] else None
    return f"no stop: t = {num(s['t'])} (the line: an average below {money(line)} a trade)"


def vh_stop(rule, s):
    if rule not in VH_BAR:
        return "-"
    _, avg, sd = VH_BAR[rule]
    if s["n"] < VH_STOP_FROM:
        return f"from {VH_STOP_FROM} trades"
    line = avg - 2 * sd / math.sqrt(s["n"])
    return f"**STOP** (avg < {money(line)})" if s["avg"] < line else f"ok (line {money(line)})"


def states_text(day_rows):
    count = {}
    for *_, d in day_rows:
        count[d.get("state") or "?"] = count.get(d.get("state") or "?", 0) + 1
    return ", ".join(f"{n} {k}" for k, n in sorted(count.items(), key=lambda kv: -kv[1]))


def report(root, today):
    sk, sk_early = load(root, *STACK)
    vh, vh_early = load(root, *VH)
    skr, vhr = rows_of(sk, STACK[0]), rows_of(vh, VH[0])
    s = block(skr)
    out = [f"# Stack shadow report ({today.isoformat()})", "",
           f"Made by stack_report.py from {root}/<draft>/days/*.json; bars: STACK_BAR.md (stack), SHADOW_BAR.md (the 3 earlier rules).", "",
           f"## 1. The stack (nq_sk_*: {len(sk)} drafts, {len({r for r in map(lambda n: rule_of(n, STACK[0]), sk)})} rules), from {STACK[1]}", ""]
    if not s["days"]:
        waiting = sorted({r[0] for r in skr})
        out.append("**No stack day has started yet.** " + (f"Day files so far: {len(skr)}, all waiting ({', '.join(waiting)})."
                                                            if skr else "No day file yet."))
    else:
        out += [HEAD, "| " + cells(s) + " |"]
    weeks4 = (today - dt.date.fromisoformat(STACK[1])).days >= 28                         # STACK_BAR 2: judged after 4 weeks
    under = sorted(n for n in sk if (b := block([r for r in skr if r[1] == n]))["fid"] is not None and b["fid"] < FIDELITY)
    sdays = sorted({r[0] for r in skr if r[3].get("state") != "waiting"})
    check_day = bool(sdays) and not any(d < sdays[-1] and d[:7] == sdays[-1][:7] for d in sdays)
    out += ["",
            f"- Stop check (STACK_BAR 3, monthly): {stack_stop(s, check_day)}.",
            f"- The read (STACK_BAR 4): {READ_DATE.isoformat()}, {(READ_DATE - today).days} days from today. Pass = 300+ trades, t >= 1 "
            "after one more tick a side, win rate >= break-even.",
            f"- Fidelity: {s['ok']} of {s['done']} finished draft-days matched the backtest, {s['bad']} did not, "
            f"{s['done'] - s['ok'] - s['bad']} not checked yet. Bar: >= 90 % per draft, judged from 4 weeks on. Under 90 %: "
            f"{(', '.join(under) or 'none') if weeks4 else 'not judged before 4 weeks (now: ' + (', '.join(under) or 'none') + ')'}.",
            "- Expected from the in-sample months: 9.0 trades a day, +$204 a trade (in-sample has not carried to test months).",
            f"- Left out: {sk_early} day files dated before {STACK[1]} (the switch-on replay)." if sk_early else "",
            "", "## 2. The stack per rule (its sessions together)", "",
            "| Rule | Drafts | " + HEAD[2:].split("\n")[0], "|---|---|" + HEAD.split("\n")[1][1:]]
    for rule in sorted({r[2] for r in skr}):
        b = block([r for r in skr if r[2] == rule])
        out.append(f"| {rule} | {b['drafts']} | {cells(b)} |")
    sb, sb_early = load(root, *SB)
    sbr = rows_of(sb, SB[0])
    t = block(sbr)
    sb_read = dt.date.fromisoformat(SB[1]) + dt.timedelta(weeks=26)
    sdays_b = sorted({r[0] for r in sbr if r[3].get("state") != "waiting"})
    check_b = bool(sdays_b) and not any(d < sdays_b[-1] and d[:7] == sdays_b[-1][:7] for d in sdays_b)
    out += ["", f"## 2b. Stack B (nq_sb_*: {len(sb)} drafts; Amendment L; STACK_BAR.md 'Stack B'), from {SB[1]}", ""]
    if not t["days"]:
        out.append("**No stack B day has started yet.**" + (f" Day files so far: {len(sbr)}." if sbr else " No day file yet."))
    else:
        out += [HEAD, "| " + cells(t) + " |", "", "| Rule | Drafts | " + HEAD[2:].split("\n")[0], "|---|---|" + HEAD.split("\n")[1][1:]]
        for rule in sorted({r[2] for r in sbr}):
            b = block([r for r in sbr if r[2] == rule])
            out.append(f"| {rule} | {b['drafts']} | {cells(b)} |")
    out += ["", f"- Stop check (monthly, from {STOP_FROM} trades): {stack_stop(t, check_b)}.",
            f"- The read: {sb_read.isoformat()}, {(sb_read - today).days} days from today. Pass = 150+ trades, t >= 1 after one more tick a "
            "side, win rate >= break-even. Expected in-sample: 2.42 trades a day, +$107 a trade.",
            f"- Left out: {sb_early} day files dated before {SB[1]}." if sb_early else ""]
    out += ["", f"## 3. The 3 earlier rules apart (nq_vh_*, from {VH[1]}; SHADOW_BAR.md)", "",
            "| Rule | Drafts | " + HEAD[2:].split("\n")[0] + " Stop (SHADOW_BAR 2) |", "|---|---|" + HEAD.split("\n")[1][1:] + "---|"]
    for rule in sorted({r[2] for r in vhr}):
        b = block([r for r in vhr if r[2] == rule])
        out.append(f"| {VH_BAR.get(rule, (rule,))[0]} | {b['drafts']} | {cells(b)} | {vh_stop(rule, b)} |")
    if vhr:
        out.append(f"| **All 3** | {len(vh)} | {cells(block(vhr))} | - |")
    else:
        out.append("No day file yet.")
    if vh_early:
        out.append(f"\nLeft out: {vh_early} day files dated before {VH[1]}.")
    allr = skr + sbr + vhr
    tags = {date: TAGGER(date) for date in sorted({r[0] for r in allr if r[3].get("state") != "waiting"})}
    mark = lambda date: {True: "M", False: "o", None: "?"}[tags.get(date)]           # noqa: E731
    out += ["", "## 4. The stack day by day (Day: M = middle-third day, o = other, ? = no prints yet)", "",
            "| Date | Day | Drafts (state) | Trades | Net $ | Cumulative $ |", "|---|---|---|---|---|---|"]
    cum = 0.0
    for date in sorted({r[0] for r in skr}):
        dr = [r for r in skr if r[0] == date]
        b = block(dr)
        cum += b["net"]
        out.append(f"| {date} | {mark(date)} | {states_text(dr)} | {b['n']} | {money(b['net'])} | {money(cum)} |")
    mid = [float(t.get("net") or 0) for date, *_, d in allr if tags.get(date) is True for t in d.get("trades") or []]
    oth = [float(t.get("net") or 0) for date, *_, d in allr if tags.get(date) is False for t in d.get("trades") or []]
    out += ["", "## 5. The middle-third skip (Amendment M; every shadow trade of every copy; shown, read ONCE at the stacks' read dates)", ""]
    if mid and oth:
        m, o = stats(mid), stats(oth)
        se = math.sqrt((m["se"] or 0) ** 2 + (o["se"] or 0) ** 2) if m["se"] and o["se"] else None
        diff = o["avg"] - m["avg"]
        out += ["| Days | Trades | Share | Avg trade $ | Win |", "|---|---|---|---|---|",
                f"| Middle | {m['n']} | {pct(m['n'] / (m['n'] + o['n']))} | {money(m['avg'])} | {pct(m['win'])} |",
                f"| Other | {o['n']} | {pct(o['n'] / (m['n'] + o['n']))} | {money(o['avg'])} | {pct(o['win'])} |", "",
                f"Other minus middle: {money(diff)} a trade, t = {num(diff / se) if se else '-'} (the read needs t >= 1, other-day avg > 0, middle share >= 20 %).",
                f"Days tagged: {sum(1 for v in tags.values() if v is True)} middle, {sum(1 for v in tags.values() if v is False)} other, {sum(1 for v in tags.values() if v is None)} untagged."]
    else:
        out.append(f"Not enough yet: {len(mid)} trades on middle days, {len(oth)} on other days.")
    ftags = {date: FLAT_TAGGER(date) for date in sorted({r[0] for r in allr if r[3].get("state") != "waiting"})}
    flat = [float(t.get("net") or 0) for date, *_, d in allr if ftags.get(date) is True for t in d.get("trades") or []]
    nof = [float(t.get("net") or 0) for date, *_, d in allr if ftags.get(date) is False for t in d.get("trades") or []]
    out += ["", "## 6. The flat open (Note N; every shadow trade of every copy; shown, read ONCE at the stacks' read dates)", ""]
    if flat and nof:
        f, o = stats(flat), stats(nof)
        se = math.sqrt((f["se"] or 0) ** 2 + (o["se"] or 0) ** 2) if f["se"] and o["se"] else None
        diff = o["avg"] - f["avg"]
        out += ["| Days | Trades | Share | Avg trade $ | Win |", "|---|---|---|---|---|",
                f"| Flat open | {f['n']} | {pct(f['n'] / (f['n'] + o['n']))} | {money(f['avg'])} | {pct(f['win'])} |",
                f"| Other | {o['n']} | {pct(o['n'] / (f['n'] + o['n']))} | {money(o['avg'])} | {pct(o['win'])} |", "",
                f"Other minus flat: {money(diff)} a trade, t = {num(diff / se) if se else '-'} (the read needs t >= 1, other-day avg > 0, flat share >= 20 %).",
                f"Days tagged: {sum(1 for v in ftags.values() if v is True)} flat, {sum(1 for v in ftags.values() if v is False)} other, {sum(1 for v in ftags.values() if v is None)} untagged."]
    else:
        out.append(f"Not enough yet: {len(flat)} trades on flat-open days, {len(nof)} on other days.")
    odd = [(r[0], r[1], r[3]) for r in skr + sbr + vhr if r[3].get("state") in ("stopped", "off", "unreadable")]
    if odd:
        out += ["", "Stopped / off draft-days:"] + [f"- {date} {name}: {d.get('state')} -- {d.get('why') or 'no reason given'}"
                                                   for date, name, d in sorted(odd, key=lambda x: (x[0], x[1]))]
    return "\n".join(out) + "\n"


def selftest():
    global TAGGER, FLAT_TAGGER
    TAGGER = lambda date: {"2026-10-22": True, "2026-10-23": False}.get(date)      # noqa: E731 - fake tags, no tape
    FLAT_TAGGER = lambda date: {"2026-10-22": False, "2026-10-23": True}.get(date)  # noqa: E731
    def day(state, nets=(), ok=None, why=None):
        return {"state": state, "why": why, "trades": [{"side": "long", "net": n, "reason": "tp" if n > 0 else "sl"} for n in nets],
                "net": float(sum(nets)), "match": None if ok == "none" else {"ok": ok, "text": ""}}

    with tempfile.TemporaryDirectory() as tmp:
        root, today = Path(tmp), dt.date(2026, 10, 21)
        assert "No stack day has started yet" in report(root, today) and "No day file yet" in report(root, today)
        files = {"nq_sk_disp15_nyam": {"2026-10-21": day("done", [9999], True),                  # replay: left out
                                       "2026-10-22": day("done", [500, -250], True),
                                       "2026-10-23": day("done", [-250], False)},
                 "nq_sk_disp15_mid": {"2026-10-22": day("stopped", [100], None, "Killed today.")},
                 "nq_sk_orbcl_pm": {"2026-10-23": day("running", [300], "none"), "2026-10-24": day("waiting", ok="none")},
                 "nq_vh_rvbrk_nyam": {"2026-10-21": day("done", [7777], True), "2026-10-22": day("done", [100, -50], True)}}
        for name, days in files.items():
            (root / name / "days").mkdir(parents=True)
            for date, d in days.items():
                (root / name / "days" / f"{date}.json").write_text(json.dumps(d))
        (root / "nq_sk_disp15_pm" / "days").mkdir(parents=True)
        (root / "nq_sk_disp15_pm" / "days" / "2026-10-22.json").write_text("{half")     # a broken file is reported, not fatal

        sk, early = load(root, *STACK)
        assert early == 1 and set(sk) == {"nq_sk_disp15_nyam", "nq_sk_disp15_mid", "nq_sk_orbcl_pm", "nq_sk_disp15_pm"}
        assert rule_of("nq_sk_disp15_nyam", "nq_sk_") == "disp15" and rule_of("nq_sk_onrorb15_nyam", "nq_sk_") == "onrorb15"
        s = block(rows_of(sk, "nq_sk_"))
        a = np.array([500, -250, -250, 100, 300.0])
        assert s["n"] == 5 and s["net"] == 400 and s["days"] == 2                    # 10-24 only waiting: not a day
        assert abs(s["be"] - 250 / (300 + 250)) < 1e-12 and abs(s["win"] - 0.6) < 1e-12
        assert abs(s["t"] - a.mean() / (a.std(ddof=1) / math.sqrt(5))) < 1e-12
        assert s["done"] == 2 and s["ok"] == 1 and s["bad"] == 1 and s["fid"] == 0.5   # stopped, running, unreadable left out
        text = report(root, today)
        assert "| 2 | 5 | 2.50 | +400 | +80 |" in text, text
        assert "Killed today." in text and "1 running, 1 waiting" not in text and "| 2026-10-24 | ? | 1 waiting | 0 |" in text
        assert "| 2026-10-23 | o | 1 done, 1 running | 2 | +50 | +400 |" in text, text
        assert "183 days from today" in text and "not checked yet: 5 of 100 trades" in text
        assert "not judged before 4 weeks (now: nq_sk_disp15_nyam)" in text and "1 day files dated before 2026-10-22" in text
        assert "| RVOL break 5m | 1 | 1 | 2 | 2.00 | +50 | +25 |" in text and "from 30 trades" in text, text
        assert "## 6. The flat open" in text and "Days tagged: 1 flat, 1 other, 0 untagged." in text, text
        assert "| Flat open | 2 | " in text, text                                      # 10-23: the -250 and the 300 (the running draft's trade counts)

    nets = [-1000.0, -900.0] * 50
    assert stack_stop(stats(nets)).startswith("**STOP**") and stack_stop(stats([100.0, -90.0] * 50)).startswith("no stop")
    assert vh_stop("rvbrk", stats([-600.0, -700.0] * 15)).startswith("**STOP**") and vh_stop("rvbrk", stats([50.0, -40.0] * 15)).startswith("ok")
    print("selftest ok")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    else:
        OUT.write_text(report(DESKLAB, dt.date.today()))
        print(OUT.read_text())
