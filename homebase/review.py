"""Morning review: what actually happened, and how it compares to the model.

    python -m homebase.review            # today
    python -m homebase.review 2026-09-17 # a specific ET date

Reads the journal only — never the broker, never places anything. The
headline number is FILL vs ANCHOR: the research modelled 1 tick of slippage
per side, and the edge is only 2-4 ticks deep, so this is the measurement
that decides whether the live strategy is the backtested strategy.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

from .config import load as load_cfg
from .contracts import point_value, tick_size
from .paths import state_dir
from .timer import fire_clock, fire_said, fire_time, late_why, miss_why, off_anchor

BAD = {"place_failed", "timer_error", "timer_missed", "clock_error", "both_filled_emergency",
       "hook_rejected", "alert_refused", "cancel_raced_fill"}


def _loud(e: dict) -> bool:
    """A timer fire past its grace, or off the pre-open anchor: a problem even
    when it placed (timer.FIRE_LATE_MAX_S, timer.off_anchor)."""
    return e.get("event") == "timer_fired" and off_anchor(e)


def events(date: str) -> list[dict]:
    p = state_dir() / "journal.jsonl"
    if not p.exists():
        return []
    out = []
    for line in p.read_text().splitlines():
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if str(r.get("et", "")).startswith(date):
            out.append(r)
    return out


def review(date: str) -> str:
    cfg = load_cfg()
    evs = events(date)
    L: list[str] = []
    add = L.append
    add(f"MORNING REVIEW — {date}")
    add("=" * 62)
    if not evs:
        add("no journal entries for this date.")
        return "\n".join(L)

    by = lambda name: [e for e in evs if e.get("event") == name]  # noqa: E731

    # --- did it fire, and how fast (chronological) ---
    add("\nSIGNAL")
    sig = {"timer_gate", "timer_skipped", "timer_waiting", "timer_missed", "timer_fired",
           "dry_run"}
    seen_missed = False
    for e in sorted((x for x in evs if x.get("event") in sig),
                    key=lambda x: x.get("ts", 0)):
        t, ev = e["et"][11:19], e["event"]
        if ev == "timer_gate":
            add(f"  {t}  gate {e.get('gate')} (ADX {e.get('adx')}, {e.get('bars')} bars)")
        elif ev == "timer_skipped":
            who = f" {e['account']}" if e.get("account") else ""
            add(f"  {t}  SKIPPED{who} — {e.get('reason')}")
        elif ev == "timer_waiting":    # said once, when the wait starts
            add(f"  {t}  WAITING for a fresh quote — {e.get('strategy')}: {e.get('text')}")
        elif ev == "timer_missed":
            if e.get("reason"):        # said once per strategy per day (timer._closed)
                add(f"  {t}  MISSED {e.get('strategy')} — {miss_why(e.get('reason'))} "
                    f"({e.get('window_end')})"
                    + (f", last: {e.get('text')}" if e.get("text") else "") + "; nothing placed")
            elif not seen_missed:      # older journals: one line, however many restarts
                add(f"  {t}  MISSED the window (service restarted after "
                    f"{e.get('window_end')})")
                seen_missed = True
        elif ev == "timer_fired" and _loud(e):
            what = "FIRED LATE" if e.get("late") is True else "FIRED OFF THE PRE-OPEN ANCHOR"
            fire = fire_time(cfg.strategies.get(e.get("strategy")))
            add(f"  {t}  {what} at {fire_clock(e.get('late_s'), fire)}, {e.get('late_s')} s past "
                f"{fire:%H:%M:%S} — {late_why(e.get('reason'), e.get('late_s'), e.get('waited_s'), e.get('wait_reason'))} · "
                f"anchor {e.get('anchor')}, the latest trade then (not the last before the "
                f"open) · accepted={e.get('result')}" + (f" · {e.get('note')}" if e.get("note") else ""))
        elif ev == "timer_fired":
            add(f"  {t}  FIRED · anchor {e.get('anchor')} · accepted={e.get('result')}"
                + (f" · {e.get('note')}" if e.get("note") else ""))
        else:
            add(f"  {t}  DRY RUN ({e.get('source')}) — would place "
                f"{e.get('upper')} ▲ / {e.get('lower')} ▼ on {e.get('account')}")

    # --- orders ---
    placed = by("placed")
    if placed:
        add("\nORDERS")
        for e in placed:
            ms = e.get("place_ms")
            add(f"  {e['et'][11:19]}  {e.get('account')} × {e.get('qty')} · "
                f"{e.get('upper')} ▲ / {e.get('lower')} ▼" +
                (f" · resting in {ms} ms" if ms is not None else ""))

    # --- fills: the measurement that matters ---
    fills = by("entry_fill")
    if fills:
        add("\nENTRY FILL vs ANCHOR   (the research modelled 1 tick/side)")
        for e in fills:
            name = e.get("strategy", "")
            sym = getattr(cfg.strategies.get(name), "symbol", "NQ")
            ts, pv = tick_size(sym), point_value(sym) or 0
            slip = e.get("fill_vs_anchor")
            qty = next((p.get("qty") for p in placed
                        if p.get("account") == e.get("account")
                        and p.get("strategy") == name), 1) or 1
            add(f"  {e['et'][11:19]}  {e.get('account')}  {e.get('side')} "
                f"@ {e.get('fill')}  (anchor {e.get('anchor')})")
            if slip is not None and ts:
                ticks = slip / ts
                # a Buy filling ABOVE the trigger is adverse; Sell below is
                signed = ticks if e.get("side") == "Buy" else -ticks
                cost = abs(slip) * pv * qty
                verdict = ("as modelled" if abs(signed) <= 1.01 else
                           "WORSE than modelled" if signed > 1 else "better than modelled")
                add(f"           slippage {slip:+.2f} pts = {signed:+.1f} ticks "
                    f"→ ${cost:,.2f} on {qty} · {verdict}")
            if "sibling_cancelled" in e:        # the first fill only
                add(f"           sibling cancelled: {e.get('sibling_cancelled')}"
                    + (f" ({e.get('sibling_error')})" if e.get("sibling_error") else ""))
    for e in by("brackets_moved"):
        mv = e.get("moved")
        add(f"  {e['et'][11:19]}  SL/TP to the fill ({e.get('fill')}): "
            f"SL {e.get('sl')} · TP {e.get('tp')} · "
            + ("moved" if mv is True else str(mv) if mv else
               f"NOT MOVED — {e.get('error')} (trigger brackets still protect)"))
    for e in by("fill_matched_by_side"):
        add(f"  ⚠ {e['et'][11:19]}  fill had no order id — matched by side "
            f"({e.get('side')})")

    # --- exits ---
    exits = by("exit_fill")
    if exits or by("clock_flat") or by("cancelled_unfilled"):
        add("\nEXIT")
        for e in exits:
            add(f"  {e['et'][11:19]}  {e.get('account')}  {str(e.get('reason')).upper()} "
                f"@ {e.get('fill')}  →  ${e.get('pnl'):,.2f} gross")
            # EXIT slippage: a triggered stop becomes a market order, so this
            # is where real slippage lives. Compare to the bracket's level.
            name = e.get("strategy", "")
            mine = lambda x: (x.get("account") == e.get("account")  # noqa: E731
                              and x.get("strategy") == name)
            ent = next((f for f in reversed(fills) if mine(f)), None)
            mv = next((m for m in reversed(by("brackets_moved"))
                       if mine(m) and m.get("sl") is not None), None)
            scfg = cfg.strategies.get(name)
            if ent and scfg and e.get("fill") is not None and ent.get("anchor") is not None:
                sym = scfg.symbol
                ts_, pv_ = tick_size(sym), point_value(sym) or 0
                sgn = 1 if ent.get("side") == "Buy" else -1
                reason = str(e.get("reason"))
                if mv and reason in ("sl", "tp"):     # re-priced to the fill
                    level = mv["sl"] if reason == "sl" else mv["tp"]
                else:
                    level = (ent["anchor"] - sgn * scfg.sl_pts if reason == "sl" else
                             ent["anchor"] + sgn * scfg.tp_pts if reason == "tp" else None)
                if level is not None and ts_:
                    # adverse = worse than the level, from the position's view
                    adverse = (level - e["fill"]) * sgn
                    ticks = adverse / ts_
                    qty = next((p.get("qty") for p in placed if mine(p)), 1) or 1
                    verdict = ("as modelled" if abs(ticks) <= 1.01 else
                               "WORSE than modelled" if ticks > 1 else "better")
                    add(f"           {reason.upper()} level {level} · slippage "
                        f"{ticks:+.1f} ticks → ${abs(adverse) * pv_ * qty:,.2f} · {verdict}")
        for e in by("cancelled_unfilled"):
            add(f"  {e['et'][11:19]}  {e.get('account')}  no fill — entries cancelled")
        for e in by("clock_flat"):
            add(f"  {e['et'][11:19]}  {e.get('account')}  flattened by the 15:55 clock")

    # --- trouble ---
    bad = sorted((e for e in evs if e.get("event") in BAD or _loud(e)),
                 key=lambda x: x.get("ts", 0))
    add("\nPROBLEMS" if bad else "\nPROBLEMS — none")
    missed = set()
    for e in bad:
        if _loud(e):
            add(f"  {e['et'][11:19]}  {e.get('strategy')} {fire_said(e)}")
            continue
        if e.get("event") == "timer_missed":
            if e.get("strategy") in missed:    # older journals: one per restart
                continue
            missed.add(e.get("strategy"))
        rest = {k: (v[:60] + "…" if isinstance(v, str) and len(v) > 60 else v)
                for k, v in e.items() if k not in ("ts", "et", "event")}
        add(f"  {e['et'][11:19]}  {e['event']}: {json.dumps(rest)[:140]}")

    # --- bottom line ---
    total = sum(float(e.get("pnl") or 0) for e in exits)
    if exits:
        add(f"\nNET (gross, before commissions): ${total:,.2f}")
    add("\nNote: pnl is gross. Measured Apex fees: ~$3.10/contract round turn "
        "(2026-09-18); the research assumed $4.00.")
    return "\n".join(L)


if __name__ == "__main__":
    d = sys.argv[1] if len(sys.argv) > 1 else \
        dt.datetime.now().astimezone().date().isoformat()
    print(review(d))
