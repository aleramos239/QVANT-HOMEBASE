"""Daily results card for @qvanttrading: one day's fills for one account, as
a 4:5 post (1080x1350) and a story (1080x1920).

Source: the desk's own /api/strategy-live (real fills only, from the journal).
Every card shows the account's mode (PAPER / LIVE) and a risk line; losses are
ink with a minus sign, gains green. Net = gross minus fees, as the desk computes.

    python -m tools.instagram.daily_card --account paper-5 --date 2026-10-12 \
        --out ~/Obsidian/Vault/30-Projects/Qvant/instagram/daily
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from datetime import date as _date
from pathlib import Path

from .brand import GAIN, INK, MUTED, esc, header, mark, page, render, HANDLE

API = "http://127.0.0.1:8850/api/strategy-live?strategy={s}"
RISK = ("Trading futures involves substantial risk of loss and is not suitable for "
        "everyone. {mode_line} Past results do not guarantee future results.")


def fetch(strategy: str) -> dict:
    with urllib.request.urlopen(API.format(s=strategy), timeout=15) as r:
        return json.load(r)


def money(v: float, sign: bool = False) -> str:
    s = f"{abs(v):,.0f}" if abs(v) >= 100 else f"{abs(v):,.2f}"
    if v < 0:
        return f"−${s}"
    return (f"+${s}" if sign and v > 0 else f"${s}")


def tone(v: float) -> str:
    return GAIN if v > 0 else INK


def spark(points: list[float], w: int, h: int) -> str:
    if len(points) < 2:
        return ""
    lo, hi = min(points + [0.0]), max(points + [0.0])
    span = (hi - lo) or 1.0
    xs = [i * (w - 24) / (len(points) - 1) + 8 for i in range(len(points))]
    ys = [h - 6 - (p - lo) / span * (h - 12) for p in points]
    zero = h - 6 - (0 - lo) / span * (h - 12)
    d = " ".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, ys))
    return (f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" fill="none">'
            f'<line x1="0" x2="{w}" y1="{zero:.1f}" y2="{zero:.1f}" stroke="rgba(22,23,26,.22)" '
            f'stroke-width="2" stroke-dasharray="6 8"/>'
            f'<polyline points="{d}" stroke="{INK}" stroke-width="4" stroke-linejoin="round" '
            f'stroke-linecap="round"/>'
            f'<circle cx="{xs[-1]:.1f}" cy="{ys[-1]:.1f}" r="8" fill="{INK}"/></svg>')


def summarize(trades: list[dict], account: str, day: str) -> dict:
    mine = sorted((t for t in trades if t["account"] == account and t["date"] <= day),
                  key=lambda t: t["date"])
    today = [t for t in mine if t["date"] == day]
    if not today:
        raise SystemExit(f"no fills for account {account!r} on {day}")
    per_day: dict[str, float] = {}
    for t in mine:
        per_day[t["date"]] = per_day.get(t["date"], 0.0) + t["net"]
    cum, run = [], 0.0
    for d in sorted(per_day):
        run += per_day[d]
        cum.append(run)
    wins = sum(1 for t in mine if t["gross"] > 0)
    return {"today": today, "n": len(mine), "wins": wins, "net": run,
            "day_net": sum(t["net"] for t in today), "cum": cum,
            "days": len(per_day), "since": min(per_day)}


def card_html(s: dict, day: str, mode: str, label: str, w: int, h: int) -> str:
    d = _date.fromisoformat(day)
    live = mode.upper() == "LIVE"
    pill_bg, pill_fg = (INK, "#fff") if live else ("transparent", INK)
    mode_line = ("Live account results." if live else
                 "Simulated (paper) account results; not live trading.")
    rows = ""
    for t in s["today"][:4]:
        side = "Long" if t["side"] == "Buy" else "Short"
        why = {"tp": "Target", "sl": "Stop"}.get(t["reason"], str(t["reason"]).upper())
        rows += (
            f'<div class="row"><div class="mono sd">{side}</div>'
            f'<div class="mono px">{t["entry"]:,.2f} → {t["exit"]:,.2f}</div>'
            f'<div class="why">{esc(why)}</div>'
            f'<div class="mono pnl" style="color:{tone(t["net"])}">{money(t["net"], True)}</div></div>')
    n, wins = s["n"], s["wins"]
    story = h > 1500
    css = f"""
.pill{{font-family:'Manrope';font-weight:700;font-size:26px;letter-spacing:.14em;padding:12px 24px;
  border-radius:999px;border:2px solid {INK};background:{pill_bg};color:{pill_fg}}}
.date{{font-size:{104 if story else 92}px}}
.sub{{margin-top:18px;font-size:34px;color:{MUTED}}}
.row{{display:grid;grid-template-columns:130px 1fr 120px 190px;gap:16px;align-items:baseline;
  padding:30px 0;border-top:2px solid rgba(22,23,26,.14);font-size:31px;white-space:nowrap}}
.row:last-child{{border-bottom:2px solid rgba(22,23,26,.14)}}
.sd{{font-weight:500}} .why{{color:{MUTED};font-size:30px}}
.pnl{{text-align:right;font-weight:600;font-size:42px}}
.net{{font-size:{190 if story else 168}px;line-height:1;font-weight:600;letter-spacing:-.04em}}
.rec{{display:flex;justify-content:space-between;align-items:flex-end;gap:40px}}
.risk{{font-size:25px;line-height:1.42;color:{MUTED};max-width:{930}px}}
"""
    body = f"""
<div class="slide t-platinum">
  <div class="top"><div class="brand">{mark(46)}QVANT</div><div class="pill">{'LIVE' if live else 'PAPER · SIMULATED'}</div></div>
  <div>
    <h1 class="date">{d.strftime('%a %-d %b')}</h1>
    <div class="sub">{esc(label)} · {len(s['today'])} trade{'s' if len(s['today']) != 1 else ''}, after fees</div>
  </div>
  <div>{rows}</div>
  <div class="rec">
    <div>
      <div class="small" style="margin-bottom:14px">Day</div>
      <div class="mono net" style="color:{tone(s['day_net'])}">{money(s['day_net'], True)}</div>
    </div>
    <div style="text-align:right">
      {spark(s['cum'], 330, 150)}
      <div class="small mono" style="margin-top:12px;color:{tone(s['net'])}">{money(s['net'], True)} total</div>
      <div class="small">{n} trades · {wins} wins</div>
      <div class="small">since {_date.fromisoformat(s['since']).strftime('%-d %b')}</div>
    </div>
  </div>
  <div>
    <div class="hair" style="margin-bottom:26px"></div>
    <div class="risk">{esc(RISK.format(mode_line=mode_line))}</div>
    <div class="bottom" style="margin-top:22px"><span class="handle">{HANDLE}</span><span class="handle">qvanttrading.com</span></div>
  </div>
</div>"""
    return page(body, w, h, css)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--account", required=True, help="one account only, e.g. paper-5")
    ap.add_argument("--date", required=True, help="YYYY-MM-DD (ET)")
    ap.add_argument("--strategy", default="nq930")
    ap.add_argument("--mode", choices=["paper", "live"], default=None,
                    help="default: paper if the account id starts with 'paper'")
    ap.add_argument("--label", default="NQ · 9:30 ET open")
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    mode = a.mode or ("paper" if a.account.startswith("paper") else "live")
    data = fetch(a.strategy)
    s = summarize(data["trades"], a.account, a.date)
    for tag, (w, h) in {"post": (1080, 1350), "story": (1080, 1920)}.items():
        out = a.out / f"{a.date}-{a.account}-{tag}.png"
        render(card_html(s, a.date, mode, a.label, w, h), out, w, h)
        print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
