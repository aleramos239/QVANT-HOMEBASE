"""Live metrics per strategy, aggregated straight from the journal.

Only REAL events count: entry_fill (slippage vs anchor) and exit_fill
(gross P&L the engine computed at exit). Dry runs never appear here —
the live strip earns itself trade by trade.
"""
from __future__ import annotations

import json
from pathlib import Path


def live_metrics(journal_path: Path) -> dict[str, dict]:
    out: dict[str, dict] = {}
    if not journal_path.exists():
        return out
    for line in journal_path.read_text().splitlines():
        try:
            r = json.loads(line)
        except ValueError:
            continue
        name = r.get("strategy")
        if not name:
            continue
        m = out.setdefault(name, {"trades": 0, "wins": 0, "net": 0.0,
                                  "slips": [], "days": set()})
        if r.get("event") == "entry_fill" and r.get("fill_vs_anchor") is not None:
            m["slips"].append(abs(float(r["fill_vs_anchor"])))
        if r.get("event") == "exit_fill" and r.get("pnl") is not None:
            pnl = float(r["pnl"])
            m["trades"] += 1
            m["wins"] += 1 if pnl > 0 else 0
            m["net"] += pnl
            m["days"].add(str(r.get("et", ""))[:10])
    for name, m in out.items():
        n = m.pop("trades")
        slips = m.pop("slips")
        wins = m.pop("wins")
        days = m.pop("days")
        out[name] = {
            "trades": n,
            "win_rate": (round(100.0 * wins / n, 1) if n else None),
            "net": round(m["net"], 2),
            "avg_trade": (round(m["net"] / n, 2) if n else None),
            "avg_slip_pts": (round(sum(slips) / len(slips), 3) if slips else None),
            "days": len(days),
        }
    return out


# Apex fees measured on the 2026-09-18 trade: $9.30 on a 3-contract round
# turn. The 09-17 trade also carried a one-time $25 charge, excluded here.
FEE_PER_CONTRACT_RT = 3.10


def strategy_live_detail(journal_path: Path, strategy: str, cfg) -> dict:
    """Everything the strategy's LIVE popup shows: per-day P&L for the
    calendar, the full metric table, and the trade log. Summed across every
    account running the strategy. Real fills only — dry runs and self-tests
    never produce exit_fill events."""
    from .contracts import tick_size

    scfg = cfg.strategies.get(strategy)
    sym = getattr(scfg, "symbol", "NQ")
    ts = tick_size(sym)
    placed, entries, levels, trades, unknown = {}, {}, {}, [], 0
    if journal_path.exists():
        for line in journal_path.read_text().splitlines():
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("strategy") != strategy:
                continue
            key = (str(r.get("et", ""))[:10], r.get("account"))
            ev = r.get("event")
            if ev == "placed":
                placed[key] = r
            elif ev == "entry_fill":
                entries[key] = r
            elif ev == "exit_recovered_on_reconnect":
                unknown += 1
            elif ev == "brackets_moved" and r.get("sl") is not None:
                levels[key] = (r["sl"], r["tp"])     # SL/TP re-priced to the fill
            elif ev == "exit_fill" and r.get("pnl") is not None:
                ent = entries.get(key, {})
                qty = int((placed.get(key) or {}).get("qty") or 1)
                sgn = 1 if ent.get("side") == "Buy" else -1
                anchor, efill = ent.get("anchor"), ent.get("fill")
                entry_slip = (None if anchor is None or efill is None or not ts
                              else round((efill - anchor) * sgn / ts, 1) + 0.0)
                reason = str(r.get("reason"))
                exit_slip = None
                if anchor is not None and scfg is not None and ts \
                        and r.get("fill") is not None and reason in ("sl", "tp"):
                    lv = levels.get(key)
                    level = ((lv[0] if reason == "sl" else lv[1]) if lv else
                             anchor - sgn * scfg.sl_pts if reason == "sl"
                             else anchor + sgn * scfg.tp_pts)
                    exit_slip = round((level - r["fill"]) * sgn / ts, 1) + 0.0
                gross = float(r["pnl"])
                trades.append({
                    "date": key[0], "account": key[1], "qty": qty,
                    "side": ent.get("side"), "entry": efill, "trigger": anchor,
                    "exit": r.get("fill"), "reason": reason, "gross": gross,
                    "net": round(gross - FEE_PER_CONTRACT_RT * qty, 2),
                    "entry_slip_ticks": entry_slip, "exit_slip_ticks": exit_slip,
                })

    days: dict[str, dict] = {}
    for t in trades:
        d = days.setdefault(t["date"], {"gross": 0.0, "net": 0.0,
                                        "trades": 0, "wins": 0})
        d["gross"] = round(d["gross"] + t["gross"], 2)
        d["net"] = round(d["net"] + t["net"], 2)
        d["trades"] += 1
        d["wins"] += 1 if t["gross"] > 0 else 0

    def money(v):
        return ("-$" if v < 0 else "$") + f"{abs(v):,.2f}"

    table: list[list[str]] = []
    add = lambda s, k, v: table.append([s, k, v])  # noqa: E731
    n = len(trades)
    if n:
        g = [t["gross"] for t in trades]
        wins = [x for x in g if x > 0]
        losses = [x for x in g if x < 0]
        cum = peak = mdd = 0.0
        for x in g:
            cum += x
            peak = max(peak, cum)
            mdd = max(mdd, peak - cum)
        mw = ml = cw = cl = 0
        for x in g:
            if x > 0:
                cw, cl = cw + 1, 0
            elif x < 0:
                cl, cw = cl + 1, 0
            mw, ml = max(mw, cw), max(ml, cl)
        avg_w = sum(wins) / len(wins) if wins else None
        avg_l = sum(losses) / len(losses) if losses else None
        dvals = {k: v["gross"] for k, v in days.items()}
        es = [t["entry_slip_ticks"] for t in trades if t["entry_slip_ticks"] is not None]
        xs = [t["exit_slip_ticks"] for t in trades if t["exit_slip_ticks"] is not None]
        add("Trades", "window", f"{trades[0]['date']} → {trades[-1]['date']}")
        add("Trades", "trades", str(n))
        add("Trades", "days traded", str(len(days)))
        add("Trades", "wins / losses", f"{len(wins)} / {len(losses)}")
        add("Trades", "win rate", f"{100 * len(wins) / n:.1f}%")
        add("P&L", "net (gross)", money(sum(g)))
        add("P&L", "net (after est. fees)", money(sum(t["net"] for t in trades)))
        add("P&L", "avg / trade", money(sum(g) / n))
        add("P&L", "avg win", money(avg_w) if avg_w is not None else "—")
        add("P&L", "avg loss", money(avg_l) if avg_l is not None else "—")
        add("P&L", "realized RR",
            f"1:{avg_w / -avg_l:.2f}" if avg_w is not None and avg_l else "—")
        add("P&L", "profit factor",
            f"{sum(wins) / -sum(losses):.2f}" if losses else "∞")
        add("P&L", "best / worst day",
            f"{money(max(dvals.values()))} / {money(min(dvals.values()))}")
        add("Risk", "max drawdown", money(-mdd))
        add("Streaks", "max win streak", str(mw))
        add("Streaks", "max loss streak", str(ml))
        add("Execution", "avg entry slippage",
            f"{sum(es) / len(es):+.1f} ticks" if es else "—")
        add("Execution", "avg exit slippage",
            f"{sum(xs) / len(xs):+.1f} ticks" if xs else "—")
        add("Execution", "research assumed", "1 tick / side")
    return {"strategy": strategy, "days": days, "trades": trades,
            "table": table, "unknown_exits": unknown,
            "fee_note": f"est. fees ${FEE_PER_CONTRACT_RT:.2f}/contract round turn "
                        "(measured 2026-09-18)"}
