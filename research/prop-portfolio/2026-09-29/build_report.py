#!/usr/bin/python3
"""NQ + ES prop-pilot report builder.

READS frozen outputs only (R/out/*, RE/out/*, ledger.csv, progress.md); runs no backtest, touches no
homebase code / desk / git, re-scores nothing. Re-run any time: every ES section renders from whatever
ES files exist and shows a PENDING state for the rest.

Writes  R/report/index.html          (Artifact source: <title>, <style>, content; no html/head/body tags)
        R/report/print.html          (standalone print variant, light theme, one section per page)
        R/report/NQ_ES_Prop_Pilot.pdf (headless Chrome of print.html, else matplotlib fallback)

Run:  PYTHONPATH=~/ramos-quant-homebase /usr/bin/python3 build_report.py
"""
from __future__ import annotations

import csv
import datetime as dt
import html
import json
import math
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pandas as pd

R = Path(__file__).resolve().parent
RE = R.parent / "2026-09-30-es"
OUT = R / "report"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

FIRMS = ["lucid", "lucidpro", "lucidpro_nodll", "apex", "apex_eod"]
SHORT = {"lucid": "Lucid Flex", "lucidpro": "Pro + DLL", "lucidpro_nodll": "Pro no DLL",
         "apex": "Apex user set", "apex_eod": "Apex EOD site"}
LONG = {"lucid": "Lucid Flex 50K", "lucidpro": "LucidPro 50K with $1,200 daily limit",
        "lucidpro_nodll": "LucidPro 50K, no daily limit", "apex": "Apex user rule set (Legacy label)",
        "apex_eod": "Apex EOD site rule set"}
UNCONF = {"apex", "apex_eod"}
FUND_OF = {"lucid": "flex", "lucidpro": "pro_dll", "lucidpro_nodll": "pro_nodll", "apex": "apex", "apex_eod": None}
VARIANTS = ["flex", "flex_dll", "pro_dll", "pro_nodll", "apex"]
VLONG = {"flex": "Lucid Flex funded", "flex_dll": "Lucid Flex funded + $1,200 daily limit (assumed)",
         "pro_dll": "LucidPro funded + daily limit", "pro_nodll": "LucidPro funded, no daily limit",
         "apex": "Apex Legacy PA"}
SESS = {"asia": "Asia", "london": "London", "nyam": "NY AM", "mid": "Midday", "pm": "NY PM", "all": "all"}
WFF = {"lucid": "lucid_flex"}
THRESH = 0.60

FAM_GLOSS = {
    "orb": "breakout of the opening range", "straddle": "breakout orders on both sides of the open",
    "donchian": "breakout of the N-bar high or low", "squeeze": "volatility squeeze, then release",
    "ema_ribbon": "three moving averages line up", "tema_slope": "smoothed average turns up or down",
    "ema_pullback": "dip to the 20-bar average in a trend", "supertrend": "trend-line flip",
    "rsi2": "2-bar RSI mean reversion", "vwap_band": "fade the 2-sigma VWAP band",
    "vwap_z": "fade a stretched distance from VWAP", "vwap_flip": "VWAP cross that holds",
    "pinbar": "wick reversal at a key level", "sweep_rev": "stop-run reversal",
    "ib": "first-hour range break or fade", "gap": "opening gap fill or follow",
    "tod_drift": "enter at a clock time, hold N bars", "random": "control: random entries",
    "lon_break": "London range break at the NY open", "first_bar_mom": "follow a big first bar",
    "mid_fade": "fade the morning move at lunch",
}


# ----------------------------------------------------------------------------- small helpers
def esc(s) -> str:
    return html.escape(str(s), quote=False)


def num(x):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return None if (v != v or math.isinf(v)) else v


def pc(x, d=None) -> str:
    v = num(x)
    if v is None:
        return "&mdash;"
    v *= 100
    if d is not None:
        return f"{v:.{d}f}%"
    return f"{v:.0f}%" if (abs(v) >= 10 or v == 0) else f"{v:.1f}%"


def usd(x, signed=False) -> str:
    v = num(x)
    if v is None:
        return "&mdash;"
    s = f"${abs(v):,.0f}"
    if v < 0:
        return "-" + s
    return ("+" + s) if signed and v > 0 else s


def f2(x, d=2) -> str:
    v = num(x)
    return "&mdash;" if v is None else f"{v:.{d}f}"


def g(o, *ks, default=None):
    for k in ks:
        if isinstance(o, dict):
            o = o.get(k)
        elif isinstance(o, (list, tuple)) and isinstance(k, int) and -len(o) <= k < len(o):
            o = o[k]
        else:
            return default
        if o is None:
            return default
    return o


def jload(p):
    try:
        with open(p) as fh:
            return json.load(fh)
    except Exception:
        return None


def tload(p):
    try:
        return Path(p).read_text()
    except Exception:
        return None


def S(h) -> str:
    """Mark a paragraph that is identical for NQ and ES: render_section prints it once, above the market blocks."""
    return f"<!--S-->{h}<!--/S-->"


def chip(kind, text) -> str:
    return f'<b class="c {kind}">{esc(text)}</b>'


def unconf() -> str:
    return chip("warn", "UNCONFIRMED")


def pend(msg) -> str:
    return f'<p class="pb">{chip("pend", "PENDING")} {esc(msg)}</p>'


def firm_lbl(f, short=True) -> str:
    return esc(SHORT[f] if short else LONG[f]) + (" " + unconf() if f in UNCONF else "")


def crit_chip(p, lo=None, thresh=THRESH):
    v = num(p)
    if v is None:
        return chip("pend", "PENDING")
    if v >= thresh and (lo is None or num(lo) is None or num(lo) >= thresh):
        return chip("ok", "PASS")
    if v >= thresh:
        return chip("warn", "PASS, CI < 60%")
    return chip("bad", "FAIL")


def table(head, rows, left=(0,), cls="", wide=()):
    """Compact HTML: optional end tags (</td></tr></thead></tbody>) are omitted, which is valid HTML."""
    def k_of(i):
        return ("l" if i in left else "") + ("w" if i in wide else "")
    th = "".join(f"<th{(' class=' + k_of(i)) if k_of(i) else ''}>{h}" for i, h in enumerate(head))
    out = []
    for r in rows:
        tds = []
        for i, c in enumerate(r):
            if isinstance(c, tuple):
                tds.append(f"<td{c[1]}>{c[0]}")
                continue
            k = k_of(i)
            tds.append(f"<td{(' class=' + k) if k else ''}>{c}")
        out.append("<tr>" + "".join(tds))
    return (f'<div class=tw><table{(" class=" + cls) if cls else ""}><thead><tr>{th}<tbody>{"".join(out)}</table></div>')


def kv(rows):
    return '<dl class="kv">' + "".join(f"<dt>{k}</dt><dd>{v}</dd>" for k, v in rows) + "</dl>"


# ----------------------------------------------------------------------------- rule words
def rules_words(cell, micros=None, policy=None) -> str:
    """Daily rules in plain words (cell = dict with day_lock/day_take/day_stop/max_day_tr/target_take)."""
    bits = []
    if micros:
        bits.append(f"{int(micros)} micros")
    c = cell or {}
    for key, lbl in (("day_lock", "lock"), ("day_take", "take"), ("day_stop", "day-stop")):
        v = num(c.get(key))
        if v:
            bits.append(f"{lbl} {usd(v)}")
    mt = num(c.get("max_day_tr"))
    if mt:
        bits.append(f"max {int(mt)} trade/day")
    if num(c.get("target_take")):
        bits.append("stop at target")
    if policy not in (None, "", "nan"):
        bits.append("payout at max" if str(policy) == "max" else f"payout at &ge;{usd(policy)}")
    return " &middot; ".join(bits) if bits else "no daily rules"


def rules_str_words(s) -> str:
    """'m40 L750 K1500 S- T- TT' -> words."""
    if not isinstance(s, str):
        return "&mdash;"
    d = {}
    for t in s.split():
        if t.startswith("TT"):
            d["target_take"] = 1
        elif t.startswith("tt"):
            d["target_take"] = 0
        elif t[0] == "m" and t[1:].isdigit():
            d["micros"] = int(t[1:])
        elif t[0] == "L" and t[1:].isdigit():
            d["day_lock"] = int(t[1:])
        elif t[0] == "K" and t[1:].isdigit():
            d["day_take"] = int(t[1:])
        elif t[0] == "S" and t[1:].isdigit():
            d["day_stop"] = int(t[1:])
        elif t[0] == "T" and t[1:].isdigit():
            d["max_day_tr"] = int(t[1:])
    return rules_words(d, d.get("micros"))


def sess_h(s) -> str:
    return SESS.get(s, s)


# ----------------------------------------------------------------------------- data loading
class Pilot:
    def __init__(self, key, label, root, inst, unit):
        self.key, self.label, self.root, self.inst, self.unit = key, label, Path(root), inst, unit
        self.out = self.root / "out"
        o = self.out
        self.port = jload(o / "portfolio_results.json")
        self.ho = jload(o / "holdout_results.json")
        self.man = jload(o / "holdout_manifest.json")
        self.econ = jload(o / "funded_econ.json")
        self.vi = jload(o / "holdout_validate_insample.json")   # frozen finalists re-scored on the in-sample window
        self.fees = jload(o / "fees.json") or jload(R / "fees.json") or {}
        self.a3 = tload(o / "a3p3_summary.md")
        self.progress = tload(self.root / "progress.md") or ""
        self.cand = self._cand()
        self.fund = self._fund()
        self.wfo = self._csv(o / "wf_offline_p3.csv")
        self.ledger = self._csv(self.root / "ledger.csv")
        self.verified = bool(list(o.glob("verify_part*.json")) or list(o.glob("holdout_validate*.json"))
                             or list(o.glob("verify*.md")))
        self.has_ho = bool(self.ho and self.ho.get("eval"))
        self.files = {n: (o / n).exists() for n in
                      ("portfolio_results.json", "funded_summary.md", "holdout_results.json",
                       "candidates.csv", "funded_candidates.csv", "a3p3_summary.md")}

    @staticmethod
    def _csv(p):
        try:
            return pd.read_csv(p, low_memory=False)
        except Exception:
            return None

    def _cand(self):
        want = {"firm", "config", "fam", "tf", "sess", "grid", "params", "fastpass", "trades", "net_1nq",
                "primary_model", "rules", "micros", "p1", "p3", "p5", "p5_ci_lo", "p5_ci_hi", "bust5", "eod_p5",
                "intr_p5", "lift_p5", "null_lift_p95", "flags", "wf_oos_p5", "apex_compliant", "day_stop"}
        try:
            df = pd.read_csv(self.out / "candidates.csv", usecols=lambda c: c in want, low_memory=False)
        except Exception:
            return None
        if "apex_compliant" not in df.columns:     # NQ file predates the column: same rule as a3p3_merge (no OCO family, target >= 0.2R)
            def _ok(r):
                try:
                    t = float(json.loads(r["params"]).get("tgt_r", 0.0 if r["fam"] == "tod_drift" else 2.0))
                except Exception:
                    return 0
                return int(r["fam"] not in ("orb", "straddle", "lon_break", "ib") and t >= 0.2)
            df["apex_compliant"] = df.apply(_ok, axis=1)
        return df

    def _fund(self):
        try:
            return pd.read_csv(self.out / "funded_candidates.csv", low_memory=False)
        except Exception:
            return None

    # ---- portfolio-result accessors
    def rep(self, f, kind="single"):
        return g(self.port, "firms", f, "reports", kind)

    def firm(self, f):
        return g(self.port, "firms", f)

    def mtime(self):
        ts = [p.stat().st_mtime for p in self.out.glob("*") if p.is_file()] if self.out.exists() else []
        return dt.datetime.fromtimestamp(max(ts)).strftime("%Y-%m-%d %H:%M") if ts else "no files"


def rec_for(P: Pilot, f: str):
    """The recommended (ex-ante) eval setup for firm f: stats in-sample / WF / holdout, members, rules, flags."""
    prim = g(P.firm(f), "primary") or ("intraday" if f in UNCONF else "realized")
    rec = {"firm": f, "primary": prim, "id": None, "members": [], "rules": {}, "flags": [], "is": None,
           "wf": None, "ho": None, "ho_id": None}
    man_f = None
    if P.man:
        pick = None
        for fid, fv in (P.man.get("finalists") or {}).items():
            if fv.get("firm") != f:
                continue
            roles = fv.get("roles") or [fv.get("role")]
            if "p5_single_compliant" in roles:
                pick = (fid, fv)
                break
            if "p5_single" in roles and pick is None:
                pick = (fid, fv)
        if pick:
            man_f = pick
    if man_f:
        fid, fv = man_f
        ins = fv.get("insample") or {}
        rec.update(id=fid, ho_id=fid, members=fv.get("members") or [], rules=fv.get("rules") or {},
                   flags=list(fv.get("apex_flags") or []))
        rec["is"] = {"p1": ins.get("p1"), "p2": ins.get("p2"), "p3": ins.get("p3"), "p5": ins.get("p5"),
                     "bust5": ins.get("bust5"), "ci": ins.get("ci_p5"), "eod": ins.get("eod_p5"),
                     "rlz": ins.get("realized_p5"), "intra": ins.get("intraday_p5"), "lift": ins.get("lift"),
                     "lift_ci": ins.get("lift_ci")}
        rec["wf_fallback"] = ins.get("wf_oos_p5")
        vh = g(P.vi, "eval", fid, "headline") or {}
        for k_ in ("p1", "p2", "p3"):
            if num(rec["is"].get(k_)) is None and num(vh.get(k_)) is not None:
                rec["is"][k_] = vh[k_]
        if rec["is"].get("ci") is None and vh.get("ci_p5"):
            rec["is"]["ci"] = vh["ci_p5"]
    else:
        r = P.rep(f, "single")
        if r:
            hl = r.get("headline") or r.get(prim) or {}
            rec["id"] = "single"
            rec["members"] = [{"cfg": m["name"].split("|")[0], "sess": m.get("sess"), "micros": m.get("micros"),
                               "name": m["name"]} for m in r.get("members", [])]
            rec["rules"] = r.get("cell") or {}
            rec["flags"] = []
            rec["is"] = {"p1": hl.get("p1"), "p2": hl.get("p2"), "p3": hl.get("p3"), "p5": hl.get("p5"),
                         "bust5": hl.get("bust5"), "ci": hl.get("ci_p5"), "eod": g(r, "eod", "p5"),
                         "rlz": g(r, "realized", "p5"), "intra": g(r, "intraday", "p5"),
                         "lift": g(r, "lift", prim, "lift"), "lift_ci": g(r, "lift", prim, "ci")}
            rec["wf_fallback"] = g(r, "wf_fixed", "oos_p5")
            if f in UNCONF and P.cand is not None and "apex_compliant" in P.cand.columns:
                for m in rec["members"]:
                    row = P.cand[(P.cand.firm == f) & (P.cand.config.str.endswith(m["name"]))]
                    if len(row) and num(row.iloc[0].get("apex_compliant")) == 0:
                        rec["flags"].append("APEX:not_compliant")
    # walk-forward OOS (offline, quarterly): lookup grid+session, primary model
    if P.wfo is not None and rec["members"]:
        m0 = rec["members"][0]
        grid = str(m0.get("cfg", "")).split("#")[0]
        sess = m0.get("sess")
        w = P.wfo[(P.wfo.grid == grid) & (P.wfo.sess == sess) & (P.wfo.firm == WFF.get(f, f))]
        if len(w):
            for mdl in (prim, "eod"):
                x = w[w.model == mdl]
                if len(x):
                    rec["wf"] = {"p5": float(x.iloc[0].oos_p5), "lo": num(x.iloc[0].get("oos_ci_lo")),
                                 "hi": num(x.iloc[0].get("oos_ci_hi")), "lift": num(x.iloc[0].get("oos_lift"))}
                    break
    if rec["wf"] is None and num(rec.get("wf_fallback")) is not None:
        rec["wf"] = {"p5": float(rec["wf_fallback"]), "lo": None, "hi": None, "lift": None, "fb": True}
    if P.has_ho and rec["ho_id"]:
        rec["ho"] = g(P.ho, "eval", rec["ho_id"])
    return rec


def single_is_rec(P, f):
    """True when the portfolio file's 'single' for firm f is the recommended eval setup (it is not for NQ Apex user / Apex EOD)."""
    rc = (getattr(P, "recs", None) or {}).get(f)
    r = P.rep(f, "single")
    if not rc or not r:
        return True
    a = {f"{m.get('cfg')}|{m.get('sess')}" for m in rc["members"]}
    b = {m["name"] for m in r.get("members", [])}
    return a == b


def ho_head(rec):
    return g(rec, "ho", "headline") or {}


def funded_picks(P: Pilot, variant, n=2):
    """Top funded configs for a variant with IS / WF / HO numbers."""
    picks = []
    df = P.fund
    if df is None:
        return picks
    full = df[(df.variant == variant) & (df.stage == "full")]
    if full.empty:
        return picks
    ids = []
    if P.man and P.man.get("funded"):
        mf = sorted([(v.get("rank", 99), k, v) for k, v in P.man["funded"].items() if v.get("variant") == variant],
                    key=lambda t: ((0, t[0]) if isinstance(t[0], int) else (1, str(t[0])), t[1]))  # ES adds "h1"/"h2" headline picks
        ids = [(k, v.get("cid")) for _, k, v in mf]
    rows = []
    for k, cid in ids[:n]:
        sub = full[full.cid == cid]
        if len(sub):
            # the frozen finalist is the row whose cell/policy match the manifest
            mcell = g(P.man, "funded", k, "cell")
            sub2 = sub[sub.cell.astype(str) == str(mcell)] if mcell else sub
            rows.append((k, (sub2 if len(sub2) else sub).iloc[0]))
    if len(rows) < n:
        seen = {(r["fam"], r["sess"], round(float(r["score_e_net_40"]), 2), str(r["policy"])) for _, r in rows}
        cnt = {}
        for _, r in rows:
            cnt[(r["fam"], r["sess"])] = cnt.get((r["fam"], r["sess"]), 0) + 1
        s = full.assign(_s=pd.to_numeric(full.score_e_net_40, errors="coerce")).sort_values("_s", ascending=False,
                                                                                         kind="stable")
        for _, r in s.iterrows():
            if len(rows) >= n:
                break
            key = (r["fam"], r["sess"], round(float(r["score_e_net_40"]), 2), str(r["policy"]))
            if key in seen or cnt.get((r["fam"], r["sess"]), 0) >= 2 or r["cid"] in [x[1]["cid"] for x in rows]:
                continue
            seen.add(key)
            cnt[(r["fam"], r["sess"])] = cnt.get((r["fam"], r["sess"]), 0) + 1
            rows.append((None, r))
    for k, r in rows:
        ho = g(P.ho, "funded", k, "headline") if (P.has_ho and k) else None
        ho_e = g(P.ho, "funded", k) if (P.has_ho and k) else None
        picks.append({"id": k, "row": r, "ho": ho, "ho_full": ho_e, "variant": variant})
    return picks


def parse_null(P: Pilot):
    """a3p3_summary.md '## Null' block -> {firm: {metric: (mean,p95,max,liftp95), n}}"""
    out = {}
    if not P.a3:
        return out
    inside = False
    for line in P.a3.splitlines():
        if line.startswith("## Null"):
            inside = True
            continue
        if inside and line.startswith("## "):
            break
        if not inside:
            continue
        m = re.match(r"^(.+?) n=(\d+): (.*)$", line)
        if not m:
            continue
        nm = m.group(1)
        f = ("lucid" if nm.startswith("Lucid Flex") else "lucidpro" if nm.startswith("LucidPro+DLL")
             else "lucidpro_nodll" if nm.startswith("LucidPro noDLL") else "apex_eod" if nm.startswith("Apex EOD")
             else "apex" if nm.startswith("Apex") else None)
        if not f:
            continue
        d = {"n": int(m.group(2))}
        for part in m.group(3).split(" ; "):
            mm = re.match(r"(\w+) ([\d.]+)/([\d.]+)/([\d.]+)\(([\d.]+)\)", part.strip())
            if mm:
                d[mm.group(1)] = tuple(float(mm.group(i)) for i in range(2, 6))
        out[f] = d
    return out


# ----------------------------------------------------------------------------- SVG charts (tokens via classes only)
def svg(w, h, inner, label, cls="ch"):
    return (f'<svg class="{cls}" viewBox="0 0 {w} {h}" role="img" aria-label="{esc(label)}">'
            f'{inner}</svg>')


def T(x, y, s, cls="t", anchor=None):
    c = cls + (" ta-m" if anchor == "middle" else " ta-e" if anchor == "end" else "")
    return f'<text x="{x:.0f}" y="{y:.0f}" class="{c}">{esc(s)}</text>'


def nice_ticks(lo, hi, n=4):
    if hi <= lo:
        hi = lo + 1
    raw = (hi - lo) / n
    mag = 10 ** math.floor(math.log10(raw))
    step = min((s * mag for s in (1, 2, 2.5, 5, 10) if s * mag >= raw), default=raw)
    a = math.floor(lo / step) * step
    b = math.ceil(hi / step) * step
    t = []
    v = a
    while v <= b + step * 1e-6:
        t.append(round(v, 10))
        v += step
    return t


def legend(items):
    return '<p class="lg">' + "".join(f'<span><i class="sw {c}"></i>{esc(t)}</span>' for c, t in items) + "</p>"


def chart_pass_bars(rows, labels=("In-sample", "Walk-forward", "Holdout"), none_text=("n/a", "n/a", "pending"),
                    ref=THRESH, title="P(pass within 5 days)", W=400, vmax=1.0,
                    fmt=lambda v: f"{v * 100:.0f}%"):
    k = len(labels)
    lx, rx = 104, W - 52
    bw = rx - lx
    bh, gap, gg, top = 7.5, 2, 11, 16
    pitch = k * bh + (k - 1) * gap + gg
    H = top + len(rows) * pitch + 22
    o = []
    ticks = [0, .2, .4, .6, .8, 1] if vmax == 1.0 else nice_ticks(0, vmax, 4)
    vmax = ticks[-1]
    for v in ticks:
        x = lx + bw * v / vmax
        o.append(f'<line x1="{x:.0f}" x2="{x:.0f}" y1="{top - 4}" y2="{H - 20}" class="gl"/>')
        o.append(T(x, H - 7, fmt(v), "t3", "middle"))
    if ref:
        x = lx + bw * ref / vmax
        o.append(f'<line x1="{x:.0f}" x2="{x:.0f}" y1="{top - 6}" y2="{H - 20}" class="ref"/>')
        o.append(T(x + 3, top - 7, f"{int(ref * 100)}% test", "tr"))
    for i, (lab, vals) in enumerate(rows):
        y0 = top + i * pitch
        o.append(T(lx - 6, y0 + (k * bh + (k - 1) * gap) / 2 + 3.5, lab, "tb", "end"))
        for j, v in enumerate(vals):
            y = y0 + j * (bh + gap)
            vv = num(v)
            if vv is None:
                o.append(T(lx + 3, y + bh - 0.5, none_text[j], "t3"))
                continue
            w = max(0.0, min(vmax, vv)) / vmax * bw
            o.append(f'<rect x="{lx}" y="{y:.0f}" width="{w:.0f}" height="{bh}" class="s{j}"/>')
            o.append(T(lx + w + 3, y + bh - 0.5, fmt(vv), "v"))
    return svg(W, H, "".join(o), title)


def chart_hbars(rows, title, fmt=lambda v: f"{v:,.0f}", W=400, lw=120, xlabel=""):
    """rows: [(label, value, cls)] ; cls in pos/neg/acc ; supports negatives."""
    vals = [num(r[1]) for r in rows if num(r[1]) is not None]
    lo, hi = min(vals + [0]), max(vals + [0])
    ticks = nice_ticks(lo, hi, 4)
    lo, hi = ticks[0], ticks[-1]
    rx = W - 50
    bw = rx - lw
    sc = bw / (hi - lo) if hi > lo else 1
    X = lambda v: lw + (v - lo) * sc
    bh, pitch, top = 9, 17, 6
    H = top + len(rows) * pitch + 22
    o = []
    for tv in ticks:
        o.append(f'<line x1="{X(tv):.0f}" x2="{X(tv):.0f}" y1="{top - 2}" y2="{H - 20}" class="{"ax" if tv == 0 else "gl"}"/>')
        o.append(T(X(tv), H - 7, fmt(tv), "t3", "middle"))
    for i, (lab, v, c) in enumerate(rows):
        y = top + i * pitch
        o.append(T(lw - 6, y + bh - 0.5, lab, "tb", "end"))
        vv = num(v)
        if vv is None:
            o.append(T(X(0) + 3, y + bh - 0.5, "n/a", "t3"))
            continue
        x0, x1 = X(min(0, vv)), X(max(0, vv))
        o.append(f'<rect x="{x0:.0f}" y="{y}" width="{max(0.5, x1 - x0):.0f}" height="{bh}" class="{c}"/>')
        tx = x1 + 3 if vv >= 0 else x0 - 3
        o.append(T(tx, y + bh - 0.5, fmt(vv), "v", None if vv >= 0 else "end"))
    return svg(W, H, "".join(o), title)


def chart_lines(series, xticks, title, yfmt=lambda v: f"{v * 100:.0f}%", xfmt=lambda v: f"{v:g}",
                ymax=None, W=400, H=210, ref=None):
    """series: [(name, idx, [(x,y)...])] ; idx selects colour class l0..l4 and dash."""
    ml, mr, mt, mb = 34, 78, 10, 26
    xs = [p[0] for s in series for p in s[2]]
    ys = [p[1] for s in series for p in s[2] if num(p[1]) is not None]
    if not xs or not ys:
        return ""
    x0, x1 = min(xticks), max(xticks)
    top_v = ymax or max(ys) * 1.08
    yt = nice_ticks(0, top_v, 4)
    top_v = yt[-1]
    X = lambda v: ml + (v - x0) / (x1 - x0) * (W - ml - mr)
    Y = lambda v: mt + (1 - v / top_v) * (H - mt - mb)
    o = []
    for tv in yt:
        o.append(f'<line x1="{ml}" x2="{W - mr}" y1="{Y(tv):.0f}" y2="{Y(tv):.0f}" class="gl"/>')
        o.append(T(ml - 4, Y(tv) + 3, yfmt(tv), "t3", "end"))
    for tv in xticks:
        o.append(T(X(tv), H - 8, xfmt(tv), "t3", "middle"))
    if ref is not None:
        o.append(f'<line x1="{ml}" x2="{W - mr}" y1="{Y(ref):.0f}" y2="{Y(ref):.0f}" class="ref"/>')
    ends = []
    for name, idx, pts in series:
        pts = [(x, y) for x, y in pts if num(y) is not None]
        if not pts:
            continue
        d = " ".join(f"{'M' if i == 0 else 'L'}{X(x):.0f} {Y(y):.0f}" for i, (x, y) in enumerate(pts))
        o.append(f'<path d="{d}" class="ln l{idx % 5} d{idx % 5}"/>')
        ends.append([Y(pts[-1][1]), name, idx, pts[-1][1]])
    ends.sort()
    for i in range(1, len(ends)):
        if ends[i][0] - ends[i - 1][0] < 11:
            ends[i][0] = ends[i - 1][0] + 11
    for yy, name, idx, v in ends:
        o.append(T(W - mr + 5, yy + 3, f"{name} {yfmt(v)}", f"tl l{idx % 5}"))
    return svg(W, H, "".join(o), title)


# ----------------------------------------------------------------------------- config / member text helpers
def cfg_info(cfg):
    m = re.match(r"^(?:hm2|hm|fp|screen|s)-(.+?)-tf(\d+)", str(cfg))
    return (m.group(1), int(m.group(2))) if m else (str(cfg), None)


def cfg_txt(cfg, sess=None, micros=None, cell=True):
    fam, tf = cfg_info(cfg)
    s = f"{fam} {tf}m" if tf else fam
    if sess:
        s += f", {sess_h(sess)}"
    if micros:
        s += f", {int(micros)} micros"
    if cell and "#" in str(cfg):
        s += f" (cell #{str(cfg).split('#')[1]})"
    return esc(s)


def mem_txt(name, micros=None):
    cfg, _, sess = str(name).partition("|")
    return cfg_txt(cfg, sess or None, micros, cell=False)


def cost_per_funded(p5, fee):
    p = num(p5)
    if not p or not fee:
        return None
    return fee.get("eval_fee", 0) / p + (fee.get("activation") or 0)


def fee_of(P, f):
    return g(P.firm(f), "fee") or {}


def prep(P: Pilot):
    P.recs = {f: rec_for(P, f) for f in FIRMS} if P.port else {}
    P.picks = {v: funded_picks(P, v) for v in VARIANTS} if P.fund is not None else {v: [] for v in VARIANTS}
    P.null = parse_null(P)


def nopf(P):
    return None if P.port else pend(f"{P.label}: out/portfolio_results.json not written yet.")


# ----------------------------------------------------------------------------- 1 Verdict
def stage_cell(p, lo=None):
    if num(p) is None:
        return f'{chip("pend", "PENDING")}'
    return f"{pc(p)} {crit_chip(p, lo)}"


def intra_of(rec, stage):
    if stage == "is":
        return g(rec, "is", "intra")
    return g(rec, "ho", "intraday", "p5")


def verdict_chip(P, f, rec):
    prim = rec["primary"]
    ho = ho_head(rec)
    frag = prim != "intraday"
    if num(ho.get("p5")) is not None:
        ok = ho["p5"] >= THRESH
        if not ok:
            return chip("bad", "FAIL")
        if frag and (num(g(rec, "ho", "intraday", "p5")) or 0) < THRESH:
            return chip("warn", "PASS if closed balance counts")
        return chip("ok", "PASS")
    p = num(g(rec, "is", "p5"))
    if p is None:
        return chip("pend", "PENDING")
    if p < THRESH:
        return chip("bad", "FAIL in-sample")
    return chip("warn", "PASS in-sample; holdout pending")


def setup_text_eval(rec):
    ms = "; ".join(cfg_txt(m.get("cfg") or m.get("name", "").split("|")[0], m.get("sess"), m.get("micros"))
                   for m in rec["members"])
    return f"{ms}. Daily rules: {rules_words(rec['rules'])}."


def pick_text(pk, short=False):
    r = pk["row"]
    pol = r.get("policy")
    rules = {"day_take": r.get("day_take"), "day_lock": r.get("day_lock"), "day_stop": r.get("day_stop"),
             "max_day_tr": r.get("max_day_tr")}
    return (f"{cfg_txt(r['cid'].split('|')[0], r['sess'], r['micros'])}. " + ("" if short else "Daily rules: ")
            + f"{rules_words(rules, None, pol)}.")


def sec1(P):
    if not P.port:
        return nopf(P)
    o = []
    # --- table 1: the 60% test
    rows = []
    for f in FIRMS:
        rc = P.recs[f]
        i = rc["is"] or {}
        ci = i.get("ci") or [None, None]
        wf = rc["wf"]
        h = ho_head(rc)
        cb = g(P.ho, "criterion_by_firm", f) if P.has_ho else None
        anyc = ("&mdash;" if not cb else
                f"none eligible {chip('bad', 'FAIL')}" if not cb.get("best_primary") else  # ES Apex: every finalist non-compliant
                (f"{pc(cb['best_primary'][0])} {chip('ok' if cb['pass_primary'] else 'bad', 'PASS' if cb['pass_primary'] else 'FAIL')}"))
        flags = ""
        if rc["flags"]:
            flags = " " + chip("bad", "APEX NON-COMPLIANT")
        rows.append([
            firm_lbl(f) + flags,
            stage_cell(i.get("p5"), ci[0]),
            (stage_cell(wf["p5"], wf.get("lo")) + (" &dagger;" if wf.get("fb") else "")) if wf else
            chip("pend", "NOT RUN" if P.wfo is not None else "PENDING"),
            stage_cell(h.get("p5"), (h.get("ci_p5") or [None])[0]) if h else chip("pend", "PENDING"),
            anyc,
            verdict_chip(P, f, rc),
        ])
    o.append("<h4>The 60% test: P(pass the eval within 5 trading days) &ge; 60%</h4>")
    o.append(table(["Firm", "In-sample", "Walk-forward OOS", "2025+ holdout", "Best finalist in holdout (picked after scoring)",
                    "Verdict"], rows, left=(0, 5)))
    nfb = [SHORT[f] for f in FIRMS if g(P.recs[f], "wf", "fb")]
    nrun = [SHORT[f] for f in FIRMS if not P.recs[f]["wf"]]
    wn = ("Walk-forward OOS = offline quarterly re-pick of cell and daily rules on the same family, timeframe and session."
          + (f" &dagger; {esc(', '.join(nfb))}: no re-pick row exists, so the fixed-parameter walk-forward is shown." if nfb else "")
          + (f" {esc(', '.join(nrun))}: no walk-forward row was run for this setup." if nrun and P.wfo is not None else ""))
    o.append(f'<p class="note">{wn}</p>')
    if not P.has_ho:
        o.append(pend(f"{P.label} holdout (2025 to latest) has not been scored yet. "
                      f"The three-stage test is complete only when out/holdout_results.json exists."))
    # --- table 2: ladder
    rows = []
    for f in FIRMS:
        rc = P.recs[f]
        i = rc["is"] or {}
        fee = fee_of(P, f)
        cpf = cost_per_funded(i.get("p5"), fee)
        rows.append([firm_lbl(f), "In-sample", pc(i.get("p1")), pc(i.get("p2")), pc(i.get("p3")), pc(i.get("p5")),
                     pc(i.get("bust5")), usd(cpf)])
        h = ho_head(rc)
        if h:
            rows.append(["", "Holdout", pc(h.get("p1")), pc(h.get("p2")), pc(h.get("p3")), pc(h.get("p5")),
                         pc(h.get("bust5")), usd(cost_per_funded(h.get("p5"), fee))])
        else:
            rows.append(["", "Holdout", "&mdash;", "&mdash;", "&mdash;", chip("pend", "PENDING"), "&mdash;", "&mdash;"])
    o.append("<h4>How fast: P(pass by day 1, 2, 3, 5), bust within 5 days, cost per funded account</h4>")
    o.append(table(["Firm", "Stage", "By day 1", "By day 2", "By day 3", "By day 5", "Bust &le; 5d",
                    "Cost per funded"], rows, left=(0, 1)))
    o.append('<p class="note">Cost per funded account = eval fee &divide; P(pass in 5 days) + activation fee. '
             'It assumes you abandon an eval after 5 days and buy a new one. Fees are assumptions '
             '(Lucid Pro prices from you; Flex and Apex assumed).</p>')
    # --- chart
    ch_rows = []
    for f in FIRMS:
        rc = P.recs[f]
        ch_rows.append((SHORT[f], [g(rc, "is", "p5"), g(rc, "wf", "p5"), g(ho_head(rc), "p5")]))
    o.append(legend([("s0", "In-sample"), ("s1", "Walk-forward OOS"), ("s2", "2025+ holdout")]))
    o.append(chart_pass_bars(ch_rows, title=f"{P.label} P(pass within 5 days) by stage, 60% line"))
    # --- recommended setups
    o.append("<h4>Recommended setup per firm</h4>")
    items = []
    for f in FIRMS:
        rc = P.recs[f]
        fv = FUND_OF[f]
        pk = (P.picks.get(fv) or [None])[0] if fv else None
        fund_txt = (pick_text(pk)) if pk else (
            "No funded model for this rule set." if not fv else "Funded search not finished.")
        flag = (" " + chip("bad", "NOT COMPLIANT with Apex PA rules: " + ", ".join(rc["flags"]))) if rc["flags"] else ""
        items.append((firm_lbl(f, False) + flag,
                      f"<b>Eval:</b> {setup_text_eval(rc) if rc['members'] else 'n/a'}<br><b>Funded:</b> {fund_txt}"))
    o.append(kv(items))
    # --- key risk
    rr = []
    for f in ("lucid", "lucidpro", "lucidpro_nodll"):
        rc = P.recs[f]
        i = rc["is"] or {}
        hrec = rc["ho"] or {}
        fv = FUND_OF[f]
        pk = (P.picks.get(fv) or [None])[0]
        e_closed = e_open = ho_e_closed = ho_e_open = None
        if pk:
            r = pk["row"]
            e_closed = r.get("e_net_40")
            for a in ("alt1", "alt2"):
                if r.get(a + "_model") == "intraday":
                    e_open = r.get(a + "_e40")
            if pk.get("ho_full"):
                ho_e_closed = g(pk["ho_full"], "realized", "e_net_40")
                ho_e_open = g(pk["ho_full"], "intraday", "e_net_40")
        rr.append([firm_lbl(f),
                   pc(i.get("rlz")), pc(g(hrec, "realized", "p5")) if hrec else "&mdash;",
                   pc(i.get("intra")), pc(g(hrec, "intraday", "p5")) if hrec else "&mdash;",
                   usd(e_closed), usd(e_open), usd(ho_e_closed) if pk and pk.get("ho_full") else "&mdash;",
                   usd(ho_e_open) if pk and pk.get("ho_full") else "&mdash;"])
    o.append('<div class="risk"><h4>Key risk: does Lucid break an account on the closed balance or on open losses?</h4>'
             "<p>Every Lucid number in this report assumes the account is lost only when the <b>closed (realised) "
             "balance</b> reaches the Max Loss Limit. Lucid's pages say &ldquo;account balance reached the MLL&rdquo; "
             "and do not say whether a floating loss counts. If open losses count (the Apex rule), the same strategies "
             "almost never reach the target. Both numbers, same strategy:</p>")
    o.append(table(["Lucid product", "Eval P5 closed: in-sample", "closed: holdout", "Eval P5 open P&L: in-sample",
                    "open P&L: holdout", "Funded E$40 closed: in-sample", "open P&L: in-sample",
                    "closed: holdout", "open P&L: holdout"], rr))
    o.append("<p>Why: the winning structures use wide stops (about 3 ATR) at 30 to 40 micros, so a single trade can "
             "float far below the limit and recover. A closed-balance rule never sees that dip. "
             "<b>Ask Lucid support in writing before sizing up.</b></p></div>")
    return "".join(o)


def terms():
    return ('<details class="terms"><summary>Terms in one line each</summary>' + kv([
        ("P5 / P1 / P3", "Chance an eval attempt reaches the profit target within 5 (or 1, 3) trading days, over every possible start day in the sample."),
        ("Bust", "The account hits its Max Loss Limit before reaching the target."),
        ("In-sample / WF / holdout", "In-sample = the 2021-09 to 2024 data the setups were searched on. Walk-forward = each quarter re-picks size and daily rules from the previous 12 months and is tested on the next quarter. Holdout = 2025 onward, scored once with frozen settings."),
        ("Closed vs open-P&L breach", "Three models are scored: eod (only the end-of-day balance can break the account), realised (balance after every closed trade; the Lucid headline) and intraday (floating loss counts at once; the Apex headline, and a bound for Lucid)."),
        ("Lift vs day-matched random", "P5 of the strategy minus P5 of random entries taken on the same days with the same exits and rules. A warning label, not a filter: most of the pass rate comes from the daily rules, not the signal."),
        ("Daily rules", "lock = stop for the day once a closed trade leaves the day up by that much; take = flatten and stop at that day profit; day-stop = flatten at that day loss; stop at eval target = no more trading once the eval is passed."),
        ("Micros", "Micro contracts: one NQ = 10 MNQ, one ES = 10 MES. Firm size caps are quoted in micros."),
    ]) + "</details>")


# ----------------------------------------------------------------------------- 2 Rules + baselines
def sec2_static(P):
    f0 = None
    if not P or not P.port:
        return pend("rules table needs portfolio_results.json")
    rows = []
    for f in FIRMS:
        fr = g(P.rep(f, "single"), "extras", "rules_spec", "firm_rules") or {}
        fee = g(P.firm(f), "fee") or {}
        rid = g(P.rep(f, "single"), "extras", "rules_spec", "rule_file") or "&mdash;"
        fsrc = (P.fees or {}).get(rid) or {}          # fees.json keeps the real "from you" flag; the results file marks every fee assumed
        if fsrc:
            fee = dict(fee, assumption=fsrc.get("assumption", fee.get("assumption")))
        cons = fr.get("consistency")
        rows.append([
            firm_lbl(f), f'<span class="mono">{esc(rid)}</span>', usd(fr.get("eval_target")),
            usd(fr.get("trailing_mll_eod")), usd(fr.get("lock_at_profit")) + " profit",
            ("none" if not cons else f"{int(cons * 100)}% rule"), str(fr.get("eval_min_days", "&mdash;")),
            usd(fr.get("soft_daily_loss_limit")) + " soft" if fr.get("soft_daily_loss_limit") else "none",
            f"{fr.get('cap_micros', '&mdash;')}", usd(fee.get("eval_fee")) + (f" + {usd(fee['activation'])} act." if fee.get("activation") else "") + (" (assumed)" if fee.get("assumption") else " (from you)"),
        ])
    o = ["<h4>Eval rules as modelled (50K accounts)</h4>"]
    o.append(table(["Firm", "Rule file", "Target", "Max loss (trails)", "Trail locks after", "Consistency",
                    "Min days", "Daily loss limit", "Max micros", "Eval fee"], rows, left=(0, 1)))
    o.append("<p class='note'>Max loss trails the highest end-of-day balance until the account is up by the lock "
             "level, then freezes at start + $100. Activation fees are assumed: $0 at Lucid, $85 at Apex. Apex EOD copies the Apex Legacy fee. "
             "Flatten times: Lucid 4:45 PM ET, Apex 4:59 PM ET (the model flattens by 4:10 PM ET).</p>")
    o.append("<h4>Funded (PA) rules as modelled</h4>")
    fr = [
        [firm_lbl("lucid") + " funded", "$2,000 EOD trail, locks at $50,100", "20/30/40 micros at $0/$1k/$2k profit",
         "5 days &ge; $150 profit, cycle profit &gt; 0", "$500 to $2,000 (max 50% of profit)", "5 payouts, then live"],
        [VLONG["flex_dll"], "same", "same", "same", "same", "daily limit stops the day only (value assumed)"],
        [firm_lbl("lucidpro") + " funded", "same trail", "40 micros, no scaling",
         "cycle profit &ge; $500, biggest day &le; 40%, balance &ge; $52,100 after payout", "$500 to $2,000, then $2,500", "$1,200 soft daily limit"],
        [firm_lbl("lucidpro_nodll") + " funded", "same", "same", "same", "same", "no daily limit"],
        [firm_lbl("apex") + " funded PA", "$2,500 intraday trail incl. open P&amp;L, stops at $50,100", "half size until $52,600",
         "8 days (5 &ge; $50), biggest day &le; 30%, safety net $52,600", "$500 to $2,000 (payouts 1 to 5)",
         "30% open-loss rule (about $750), no OCO or both-side orders, stop &le; 5&times; target"],
    ]
    o.append(table(["Variant", "Max loss", "Size", "Payout eligibility", "Payout size", "Other"], fr, left=(0, 1, 2, 3, 4, 5), wide=(1, 2, 3, 4, 5)))
    o.append("<p class='note'>Lucid funded split is 90/10. Apex splits 100% of the first $25k. "
             "Source: your funded-rules paste and the firms' help pages (rules_research.md, retrieved 2026-09-30).</p>")
    o.append("<h4>Apex: two rule sets, both unconfirmed</h4>")
    o.append("<p>Your set (&ldquo;Legacy&rdquo; label, $2,000 end-of-day trail, $3,000 target, 100 micros) is a hybrid. On the "
             "firm's own pages, <i>Legacy</i> is a $2,500 <b>intraday</b>-trailing product, and the separate end-of-day family "
             "(site set: $2,000, $1,000 soft daily limit, 60 micros) is also enforced in real time on open P&amp;L. "
             "Both sets are scored and flagged UNCONFIRMED. Apex PA also forbids OCO or both-side orders, stops more than "
             "5&times; the target and using the trail as a stop, so fast-pass coin-flip structures are not usable there.</p>")
    return "".join(o)


def sec2(P):
    if not P.port:
        return nopf(P)
    nl = P.null
    if not nl:
        return pend("zero-edge baseline block missing from out/a3p3_summary.md")
    rows = []
    for f in FIRMS:
        d = nl.get(f)
        if not d:
            continue
        prim_key = "P5int" if f in UNCONF else "P5rlz"
        pk = d.get(prim_key) or (None,) * 4
        eod = d.get("P5eod") or (None,) * 4
        itr = d.get("P5int") or (None,) * 4
        p1 = d.get("P1rea") or d.get("P1int") or (None,) * 4
        p3 = d.get("P3rea") or d.get("P3int") or (None,) * 4
        best = g(P.recs.get(f), "is", "p5")
        mx = pk[2]
        dd = None if best is None or mx is None else (best - mx) * 100
        flag = ("" if dd is None else
                chip("warn", "at or below zero-edge max") if dd < 0.5 else
                chip("warn", f"+{dd:.0f} pts over zero-edge max") if dd < 10 else chip("ok", f"+{dd:.0f} pts over zero-edge max"))
        rows.append([firm_lbl(f), str(d["n"]), f"{pc(pk[0])} / {pc(pk[1])} / {pc(pk[2])}",
                     f"{pc(eod[0])} / {pc(eod[2])}", f"{pc(itr[0])} / {pc(itr[2])}",
                     f"{pc(p1[0])} / {pc(p1[2])}", f"{pc(p3[0])} / {pc(p3[2])}", pc(best), flag])
    o = [S("<h4>Zero-edge baselines: the same search run on random entries</h4>"
           "<p>Random-entry configs went through the identical rules search and breach models, so these are the best a "
           "strategy with no edge can reach by tuning daily rules alone. If a real result sits near the zero-edge maximum, "
           "the rules are doing the work.</p>")]
    o.append(table(["Firm", "Random configs", "P5 primary: mean / p95 / max", "P5 closed-eod: mean / max",
                    "P5 open P&amp;L: mean / max", "P1: mean / max", "P3: mean / max", "Our rec. P5", "Read"], rows, left=(0, 8)))
    return "".join(o)


# ----------------------------------------------------------------------------- 3 Firm comparison
def sec3(P):
    if not P.port:
        return nopf(P)
    rows = []
    bars = []
    for f in FIRMS:
        rc = P.recs[f]
        i = rc["is"] or {}
        h = ho_head(rc)
        fee = fee_of(P, f)
        fk = FUND_OF[f]
        pk = (P.picks.get(fk) or [None])[0] if fk else None
        e40 = pk["row"].get("e_net_40") if pk else None
        ho_e40 = g(pk, "ho", "e_net_40") if pk else None
        en = (P.econ or {}).get(fk) if fk else None
        cp = (en or {}).get("cp") or [None] * 4
        rows.append([firm_lbl(f), pc(i.get("p5")),
                     pc(h.get("p5")) if h else chip("pend", "PENDING"),
                     usd(cost_per_funded(i.get("p5"), fee)), usd(e40), usd(ho_e40) if ho_e40 is not None else (
                         chip("pend", "PENDING") if not P.has_ho else "&mdash;"),
                     (f"<b>{usd(cp[0])}</b><small>{cfg_txt(cp[1].split('|')[0], cp[1].split('|')[1] if '|' in cp[1] else None)}</small>"
                      if cp[0] is not None and cp[1] else "n/a"),
                     usd((en or {}).get("net")) if en else "n/a", usd((en or {}).get("wf_net")) if en else "n/a"])
        bars.append((SHORT[f], cp[0], "acc"))
    o = [S("<p class=lead2>One recommended setup per firm. Headline value is the <b>same-config</b> line: the strategy that "
           "passes the eval must be the same one that gets paid when funded. The grey text under that value names the strategy (it can differ from the recommended setup in the earlier columns).</p>")]
    o.append(table(["Firm", "P5 in-sample", "P5 holdout", "Cost per funded", "Funded E$40 (IS)",
                    "Funded E$40 (holdout)", "Eval + funded value per purchase, same config",
                    "mixed best-eval x best-funded", "walk-forward-based"], rows, left=(0,)))
    o.append(S("<p class='note'>Value per purchase = P(pass in 5 days) &times; E$ to you within 60 funded days &minus; eval fee "
               "&minus; P(pass) &times; activation. &ldquo;Mixed&rdquo; pairs the best eval and best funded configs (they differ): an upper bound. "
               "No holdout value: the frozen eval and funded finalists are different configs. Apex EOD has no funded model.</p>"))
    return "".join(o)


# ----------------------------------------------------------------------------- 4 Leaderboard
def flag_chips(fl, noncomp=False):
    out = []
    mp = {"ONE_YEAR": ("warn", "ONE_YEAR"), "NO_EDGE_VS_RANDOM": ("warn", "NO_EDGE"), "NET<=0": ("bad", "NET<=0"),
          "COST_RULE_FAIL": ("warn", "COST_RULE")}
    for t in str(fl).split(";") if isinstance(fl, str) else []:
        if t in mp:
            out.append(chip(*mp[t]))
    if noncomp:
        out.append(chip("bad", "NON-COMPLIANT"))
    return " ".join(out) or "&mdash;"


def sec4(P):
    c = P.cand
    if c is None:
        return pend("out/candidates.csv missing")
    o = [S("<p class=lead2>Top three per firm by P(pass in 5 days), one row per family grid and session. "
           "<b>Lift</b> is P5 minus the day-matched random control; below the zero-edge p95 it is a warning that the daily "
           "rules, not the signal, produce the pass rate.</p>")]
    for f in FIRMS:
        d = c[c.firm == f].sort_values("p5", ascending=False)
        d = d.drop_duplicates(subset=["grid", "sess"]).head(3)
        rows = []
        for k, (_, r) in enumerate(d.iterrows(), 1):
            cfg = str(r["config"]).split("|")[1] if "|" in str(r["config"]) else r["config"]
            lift = num(r["lift_p5"])
            thr = num(r["null_lift_p95"])
            lk = ("" if lift is None else
                  chip("warn" if (thr is not None and lift <= thr) else "ok", f"{lift:+.2f} (p95 {thr:.2f})" if thr is not None else f"{lift:+.2f}"))
            nc = (f in UNCONF and (num(r.get("apex_compliant")) == 0 or (num(r.get("day_stop")) or 0) >= 2000))
            rows.append([str(k), cfg_txt(cfg, r["sess"]), rules_str_words(r["rules"]), pc(r["p1"]), pc(r["p3"]),
                         f'{pc(r["p5"])} <span class="ci">[{num(r["p5_ci_lo"]) * 100:.0f}-{num(r["p5_ci_hi"]) * 100:.0f}]</span>',
                         pc(r["bust5"]), f'{pc(r["eod_p5"])} / {pc(r["intr_p5"])}', lk, flag_chips(r["flags"], nc)])
        o.append(f"<h4>{firm_lbl(f, False)}</h4>")
        o.append(table(["#", "Config", "Size and daily rules", "P1", "P3", "P5 [95% CI]", "Bust", "P5 closed / open P&amp;L",
                        "Lift vs random", "Flags"], rows, left=(0, 1, 2, 8, 9), wide=(2,)))
    return "".join(o)


# ----------------------------------------------------------------------------- 5 Breakdowns
def exit_type(r):
    try:
        p = json.loads(r["params"]) if isinstance(r["params"], str) else {}
    except Exception:
        p = {}
    if num(r.get("fastpass")) == 1:
        return "Fast-pass: points stop, small target"
    if num(p.get("exit_bars")):
        return "Time exit (hold N bars)"
    t = num(p.get("tgt_r"))
    if t is None:
        return "Default exits"
    if t <= 0.75:
        return "ATR stop, target &le; 0.75R"
    if t <= 1.5:
        return "ATR stop, target 1R"
    return "ATR stop, target 2R or more"


def fam_gloss_block():
    return ('<details class="terms"><summary>What each family does</summary>'
            + kv([(k, v) for k, v in sorted(FAM_GLOSS.items())]) + "</details>")


def sec5(P):
    c = P.cand
    if c is None:
        return pend("out/candidates.csv missing")
    c = c.copy()
    c["exit"] = c.apply(exit_type, axis=1)
    c["tfs"] = c["tf"].astype("Int64").astype(str) + " min"
    c["sess_h"] = c["sess"].map(sess_h)
    groups = [("Family", "fam", True), ("Timeframe", "tfs", False), ("Session", "sess_h", False), ("Exit type", "exit", False)]
    o = [S("<p class=lead2>Best P(pass in 5 days) among all searched configs in each family, timeframe, session or exit type "
           "(primary breach model; shade = value). A best near the zero-edge maximum in section 2 says little about the signal.</p>")]
    for title, col, gloss in groups:
        cats = sorted(c[col].dropna().unique(), key=lambda s: -c[c[col] == s].p5.max())
        if col == "fam":
            cats = cats[:13]
        rows = []
        for cat in cats:
            r = [esc(cat) if col != "exit" else cat]
            for f in FIRMS:
                d = c[(c[col] == cat) & (c.firm == f)].p5
                if d.empty:
                    r.append("&mdash;")
                    continue
                mx = d.max()
                r.append((pc(mx), f" class=h{shade(mx, 0.85)}"))
            rows.append(r)
        sfx = f" (13 best of {c.fam.nunique()})" if col == "fam" else ""
        o.append(f"<h4>By {title.lower()}{sfx}</h4>")
        o.append(table([title] + [SHORT[f].replace("Apex user set", "Apex user").replace("Apex EOD site", "Apex EOD") for f in FIRMS],
                       rows, left=(0,), cls="hmt"))
    return "".join(o)


# ----------------------------------------------------------------------------- 6 Correlation
def shade(v, hi=1.0):
    return min(5, int(round(min(1.0, max(0.0, v / hi)) * 5)))


def heat_table(labels, M):
    rows = []
    for i, lb in enumerate(labels):
        r = [f"<b>{lb}</b>"]
        for j in range(len(labels)):
            v = num(M[i][j]) or 0.0
            r.append((f"{v:.2f}", f" class={'n' if v < 0 else 'h'}{shade(abs(v))}"))
        rows.append(r)
    return table([""] + list(labels), rows, left=(0,), cls="hmt cm")


def sec6(P):
    if not P.port:
        return nopf(P)
    figs = []
    for f in FIRMS:
        r = P.rep(f, "portfolio")
        mc = g(r, "extras", "member_corr")
        if not mc:
            continue
        names = mc["names"]
        lab = [chr(65 + i) for i in range(len(names))]
        mem = "".join(f"<li><b>{lab[i]}</b> {mem_txt(n)}</li>" for i, n in enumerate(names))
        stat = f'mean pair {f2(mc.get("pair_mean"))}, max {f2(mc.get("pair_max"))}'

        figs.append(f'<figure class="fg"><figcaption>{firm_lbl(f)}</figcaption>{heat_table(lab, mc["daily_pnl_corr"])}'
                    f'<ul class="mem">{mem}</ul><p class="note">{stat}</p></figure>')
    if not figs:
        return pend("no member_corr in portfolio_results.json")
    return (S('<p class=lead2>Correlation of the daily P&amp;L of each finalist portfolio member (in-sample). Near zero means '
              "the members win and lose on different days; they still lose together on some bad days.</p>")
            + f'<div class="cg">{"".join(figs)}</div>')


# ----------------------------------------------------------------------------- 7 Portfolio vs single
def sec7(P):
    if not P.port:
        return nopf(P)
    o = []
    rows = []
    dead_notes = []
    for f in FIRMS:
        first = True
        for kind, lbl, hid in (("single", "Single", ":single"), ("portfolio", "Portfolio (3+)", ":pf")):
            r = P.rep(f, kind)
            if not r:
                continue
            prim = r.get("primary")
            h = r.get("headline") or r.get(prim) or {}
            ex = r.get("exec") or {}
            members = ex.get("members") or []
            top = max([m.get("trade_share", 0) for m in members], default=None)
            dead = ex.get("dead") or []
            if kind == "portfolio" and dead:
                dead_notes.append((f, len(dead), len(members)))
            ho = g(P.ho, "eval", f + hid) if P.has_ho else None
            hp = g(ho, "headline", "p5")
            fl_ = g(P.man, "finalists", f + hid, "apex_flags") or []
            lbl_ = lbl + ((" " + chip("bad", "NON-COMPLIANT")) if (f in UNCONF and fl_) else "")
            lf = g(r, "lift", prim, "lift")
            lci = g(r, "lift", prim, "ci") or [None, None]
            rows.append([firm_lbl(f) if first else "", lbl_, str(len(r.get("members", []))),
                         f'{pc(h.get("p5"))} <span class="ci">[{pc((h.get("ci_p5") or [None])[0])}, {pc((h.get("ci_p5") or [None, None])[1])}]</span>',
                         pc(h.get("bust5")), (f"{lf:+.2f}" if num(lf) is not None else "&mdash;"),
                         pc(top), (pc(hp) if hp is not None else (chip("pend", "PENDING") if not P.has_ho else "&mdash;"))])
            first = False
    o.append("<h4>Does adding strategies to one account help?</h4>")
    o.append(table(["Firm", "Build", "Members", "P5 in-sample [CI]", "Bust &le; 5d", "Lift vs random", "Top member's share of executed trades",
                    "P5 holdout"], rows, left=(0, 1)))
    odd = [SHORT[f] for f in FIRMS if not single_is_rec(P, f)]
    if odd:
        o.append("<p class='note'>" + esc(", ".join(odd)) + ": the Single row is the portfolio search's own single, which is not the recommended "
                 "eval setup in section 1 (that one was chosen among Apex-compliant configs), so its numbers differ from sections 1 and 3. "
                 "NON-COMPLIANT = the setup breaks an Apex PA rule (a day-stop of $2,000 or more acts as a trailing threshold; no target or stop over 5&times; the target).</p>")
    if dead_notes:
        txt = "; ".join(f"{SHORT[f]}: {d} of {n} members" for f, d, n in dead_notes)
        o.append(S('<div class="callout"><b>Executed-share finding.</b> Under the shared daily rules (for example &ldquo;max 1 trade a day&rdquo; or '
                   "an early take/lock), later-session members often never get to trade, so the &ldquo;portfolio&rdquo; is really one strategy. "
                   "Portfolios were therefore scored on executed P&amp;L, not stand-alone P&amp;L, "
                   "and the dependable diversifier is several accounts, not several strategies in one account.</div>"))
        o.append(f"<p class='note'>Members that ran under 5% of the trades: {esc(txt)}.</p>")
    # portfolio page
    o.append("<h4>Portfolio page: members and shared rules</h4>")
    rows = []
    for f in FIRMS:
        r = P.rep(f, "portfolio")
        if not r:
            continue
        ex = {m["name"]: m for m in (g(r, "exec", "members") or [])}
        mem = []
        for m in r.get("members", []):
            e = ex.get(m["name"], {})
            mem.append(f"{mem_txt(m['name'], m.get('micros'))}: <b>{e.get('executed', 0)}</b> {'trade' if e.get('executed') == 1 else 'trades'} ({pc(e.get('trade_share'))}), {usd(e.get('net'))}")
        rows.append([firm_lbl(f), "<br>".join(mem), rules_words(r.get("cell"))])
    o.append(table(["Firm", "Members: executed trades (share of trades), executed net", "Shared daily rules"], rows,
                   left=(0, 1, 2), wide=(1, 2)))
    # multi-account
    ma = g(P.port, "multi_account", "mixes") or {}
    hm = (P.ho or {}).get("multi") or {} if P.has_ho else {}
    if ma:
        o.append("<h4>Several accounts at once: N parallel evals on distinct strategies</h4>")
        rows = []
        s_is, s_isb, s_ho, s_hob = [], [], [], []
        for n in sorted(ma, key=int):
            m = ma[n]
            p = m["primary"]
            h = hm.get(n) or {}
            hp = g(h, "primary", "p_any5")
            hci = g(h, "primary", "ci_p_any5") or [None, None]
            comp = ", ".join(f"{v}&times; {SHORT[k]}" for k, v in (m.get("counts") or {}).items())
            base = g(m, "same_strategy_baseline", "primary", "p_any5")
            rows.append([n, comp, f'{pc(p["p_any5"])} <span class="ci">[{pc((p.get("ci_p_any5") or [None])[0])}, {pc((p.get("ci_p_any5") or [None, None])[1])}]</span>',
                         pc(g(m, "intraday", "p_any5")), pc(base),
                         (f'{pc(hp)} <span class="ci">[{pc(hci[0])}, {pc(hci[1])}]</span>' if hp is not None else chip("pend", "PENDING")),
                         pc(g(h, "intraday", "p_any5")) if hp is not None else "&mdash;",
                         usd(p.get("total_eval_cost")), f2(p.get("e_funded")), usd(p.get("cost_per_funded"))])
            s_is.append((int(n), p["p_any5"]))
            s_isb.append((int(n), g(m, "intraday", "p_any5")))
            if hp is not None:
                s_ho.append((int(n), hp))
                s_hob.append((int(n), g(h, "intraday", "p_any5")))
        o.append(table(["N", "Accounts", "P(&ge;1 pass &le; 5d) in-sample", "open-P&amp;L bound", "same strategy x N", "holdout",
                        "holdout open-P&amp;L bound", "Eval cost", "Expected funded", "Cost per funded"], rows, left=(0, 1), wide=(1,)))
        ser = [("in-sample", 0, s_is), ("in-sample, open P&L", 3, s_isb)]
        if s_ho:
            ser += [("holdout", 1, s_ho), ("holdout, open P&L", 4, s_hob)]
        o.append(chart_lines(ser, [2, 3, 4, 5, 6], f"{P.label} P(at least one pass in 5 days) by number of accounts",
                             ymax=1.0, xfmt=lambda v: f"N={v:g}", ref=THRESH))
        o.append(S("<p class='note'>Mixes are greedy in-sample fillings, so the in-sample column is optimistic. "
                   "The pass events of different accounts are only weakly correlated, which is why N helps. "
                   "Cost is eval fees only (fees assumed).</p>"))
        if g(P.port, "multi_account", "preliminary"):
            o.append("<p class=note>" + chip("warn", "PRELIMINARY") + " The source file marks the multi-account mixes as preliminary.</p>")
    return "".join(o)


# ----------------------------------------------------------------------------- 8 Risk curve
def sec8(P):
    if not P.port:
        return nopf(P)
    scales = [0.25, 0.5, 0.75, 1.0, 1.25]
    s_p5, s_b5, rows = [], [], []
    for i, f in enumerate(FIRMS):
        r = P.rep(f, "single")
        rc = g(r, "extras", "risk_curve") or []
        prim = g(r, "primary")
        pts = [(x["scale"], g(x, "fixed", prim, "p5"), g(x, "fixed", prim, "bust5")) for x in rc if g(x, "fixed", prim)]
        if not pts:
            continue
        s_p5.append((SHORT[f], i, [(a, b) for a, b, _ in pts]))
        s_b5.append((SHORT[f], i, [(a, c) for a, _, c in pts]))
        d = {a: (b, c) for a, b, c in pts}
        rows.append([firm_lbl(f) + ("" if single_is_rec(P, f) else " &dagger;")] + [f"{pc(d[s][0])} <span class='ci'>({pc(d[s][1])})</span>" if s in d else "&mdash;" for s in scales])
    if not rows:
        return pend("no risk_curve in portfolio_results.json")
    o = [S("<p class=lead2>Same strategy and daily rules, every position scaled to 0.25x up to 1.25x of the recommended size "
           "(capped at the firm's contract limit). More size means a faster target but a faster bust.</p>"),
         chart_lines(s_p5, scales, f"{P.label} P(pass in 5 days) versus position size", ymax=1.0, xfmt=lambda v: f"{v:g}x", ref=THRESH)]
    o.append(table(["Firm"] + [f"{s:g}x" for s in scales], rows, left=(0,)))
    odd = [SHORT[f] for f in FIRMS if not single_is_rec(P, f)]
    o.append("<p class='note'>Cells: P(pass in 5 days) with bust in brackets, primary breach model. "
             "A flat top at 1x to 1.25x means the size cap is binding. Chart: P(pass in 5 days)."
             + (f" &dagger; {esc(', '.join(odd))}: the curve was run on the portfolio search's single, not the recommended setup, so its 1x value differs from section 1." if odd else "") + "</p>")
    return "".join(o)


# ----------------------------------------------------------------------------- 9 Day 1-5
def is_block(P, f, key):
    """In-sample by_day / news block for the RECOMMENDED eval setup of firm f.
    The portfolio file's 'single' is the recommended setup except for NQ Apex; there the frozen finalist re-scored on the in-sample window is used."""
    rc = P.recs[f]
    r = P.rep(f, "single")
    prim = g(r, "primary")
    if single_is_rec(P, f):
        return g(r, "extras", key, prim), None
    e = g(P.vi, "eval", rc.get("ho_id") or "") or {}
    return g(e, key, g(e, "headline", "model") or prim), None


def sec9(P):
    if not P.port:
        return nopf(P)
    rows = []
    odd9 = []
    for f in FIRMS:
        rc = P.recs[f]
        r = P.rep(f, "single")
        prim = g(r, "primary")
        bd, hb = is_block(P, f, "by_day")
        hb = (g(rc, "ho", "by_day", prim) or {})
        if not bd:
            odd9.append(SHORT[f])
            continue
        for lbl, key, cls in (("pass on day", "pass_on_day", "pb1"), ("bust on day", "bust_on_day", "pb2")):
            cells = []
            for i in range(5):
                v = num(g(bd, key, i))
                h = num(g(hb, key, i))
                cells.append("&mdash;" if v is None else
                             (f"{v * 100:.0f}%" + (f"<var> / {h * 100:.0f}%</var>" if h is not None else ""),
                              f" class='bc {cls}' style=--p:{min(1, v):.2f}"))
            rows.append([firm_lbl(f) if key == "pass_on_day" else "", lbl] + cells)
    if not rows:
        return pend("no by_day distribution in portfolio_results.json")
    ho_note = ("Small grey figure after the slash = 2025+ holdout." if P.has_ho else "")
    o = [S('<p class=lead2>When attempts end. Each cell is the share of all start days that pass or bust <b>on</b> that day (in-sample; bar drawn to scale, '
           f"full cell = 100%). {ho_note} The rest are still open or end the 5-day window flat.</p>"),
         table(["Firm", "Outcome", "Day 1", "Day 2", "Day 3", "Day 4", "Day 5"], rows, left=(0, 1), cls="bct"),
         S("<p class='note'>Lucid Flex cannot pass before day 2 (50% consistency, 2-day minimum), in practice day 3. "
           "Fast passes come with fast busts: where an account can pass on day 1 or 3, most busts also land on day 1 or 2. These are short, high-variance bets.</p>")]
    if odd9:
        o.append(pend(f"No in-sample day distribution for the recommended setup of {', '.join(odd9)}."))
    if not P.has_ho:
        o.append(pend(f"{P.label} holdout day distribution not available yet."))
    return "".join(o)


# ----------------------------------------------------------------------------- 10 News
def sec10(P):
    if not P.port:
        return nopf(P)
    rows = []
    for f in FIRMS:
        rc = P.recs[f]
        r = P.rep(f, "single")
        prim = g(r, "primary")
        n = is_block(P, f, "news")[0] or {}
        hn = g(rc, "ho", "news", prim) or {}
        d1 = (n.get("p5_news") or 0) - (n.get("p5_nonnews") or 0) if n else None
        rows.append([firm_lbl(f), pc(n.get("p5_news")), pc(n.get("p5_nonnews")), pc(n.get("bust5_news")), pc(n.get("bust5_nonnews")),
                     (pc(hn.get("p5_news")) if hn else (chip("pend", "PENDING") if not P.has_ho else "&mdash;")),
                     pc(hn.get("p5_nonnews")) if hn else "&mdash;", pc(hn.get("bust5_news")) if hn else "&mdash;",
                     pc(hn.get("bust5_nonnews")) if hn else "&mdash;"])
    nn = g(P.rep("lucid", "single"), "extras", "news") or {}
    o = [S(f"<p class=lead2>An attempt counts as a &ldquo;news&rdquo; attempt if a CPI, jobs or FOMC day falls inside its 5-day window "
           f"({nn.get('n_starts_with_news_in_window', '?')} news vs {nn.get('n_starts_without', '?')} non-news start days in-sample, both markets).</p>")]
    o.append(table(["Firm", "IS P5 news", "IS P5 no news", "IS bust news", "IS bust no news", "Holdout P5 news",
                    "Holdout P5 no news", "Holdout bust news", "Holdout bust no news"], rows, left=(0,)))
    o.append(S("<p class='note'>Differences of a few points are noise from overlapping start days.</p>"))
    return "".join(o)


# ----------------------------------------------------------------------------- 11 Funded
def sec11(P):
    if P.fund is None:
        return pend("out/funded_candidates.csv not written yet.")
    rows = []
    bars = []
    ho_any = False
    for v in VARIANTS:
        pks = P.picks.get(v) or []
        for k, pk in enumerate(pks, 1):
            r = pk["row"]
            ho = pk.get("ho")
            ho_any = ho_any or bool(ho)
            if ho:
                hocell = (f"<b>{usd(ho.get('e_net_40'))}</b> <span class='ci'>({pc(ho.get('p_pay_40'))} paid, "
                          f"{f2(ho.get('med_days_first'), 0)} d)</span>")
            else:
                hocell = chip("pend", "PENDING") if not P.has_ho else '<span class="ci">not a frozen finalist</span>'
            wfv = num(r.get("wf_oos_e_net_40"))
            rows.append([
                f"<b>{esc(VLONG[v])}</b>" + (" " + unconf() if v == "apex" else "") if k == 1 else "",
                f"#{k} {pick_text(pk, True)}",
                f"{pc(r.get('p_pay_20'))} / {pc(r.get('p_pay_40'))} / {pc(r.get('p_pay_60'))}",
                (f"{num(r.get('med_days_first')):.0f} d" if num(r.get("med_days_first")) is not None else "&mdash;"),
                usd(r.get("e_first_gross")), usd(r.get("e_net_40")), usd(r.get("e_net_60")), pc(r.get("p_bust_pre_first")),
                (f"{usd(wfv)} <span class='ci'>({pc(r.get('wf_oos_p_pay_40'))} paid)</span>" if wfv is not None else "&mdash;"),
                hocell])
            if k == 1:
                pass
    if not rows:
        return pend("no funded picks (stage 'full') in funded_candidates.csv yet.")
    o = [S("<p class=lead2>Objective: a high payout rate, a high payout and a short time to payout. "
           "<b>E$40</b> = expected dollars to you within 40 funded trading days (after the 90/10 split, counting accounts that bust "
           "before any payout). First cheque is the gross amount of the first payout. "
           "Payout policy = when to request: as soon as the cheque reaches that amount, or at the maximum.</p>")]
    o.append(table(["Variant", "Setup and daily rules (funded)", "P(paid) by 20 / 40 / 60 days", "Median days to first payout",
                    "E[first cheque]", "E$40", "E$60", "Bust before first payout", "Walk-forward E$40", "Holdout E$40"],
                   rows, left=(0, 1), wide=(1,)))
    notes = []
    o.append(S("<p class='note'>E$40 is the primary ranking number, taken at a stable rule cell (the lower of the cell's own value and the median of its neighbours), so a #2 row can show a slightly higher raw E$40 than #1. Apex PA numbers use the pessimistic open-loss ordering and are UNCONFIRMED.</p>"))
    if not P.has_ho:
        notes.append(f"{P.label} holdout funded results are pending.")
    if notes:
        o.append("<p class='note'>" + " ".join(notes) + "</p>")
    return "".join(o)


# ----------------------------------------------------------------------------- 12 Homebase walk-forwards
def sec12(P):
    L = P.ledger
    if L is None:
        return pend("ledger.csv missing")
    w = L[L.stage == "wf"].copy()
    if w.empty:
        return pend("no walk-forward rows in ledger.csv yet (stage 'wf').")
    w["net"] = pd.to_numeric(w["net"], errors="coerce")
    w = w.sort_values("net", ascending=False)
    mx = max(abs(w.net.max()), abs(w.net.min())) or 1
    rows = []
    for _, r in w.iterrows():
        m = re.match(r"^wf-(.+)-tf(\d+)-([a-z]+)(-fp)?$", str(r["key"]))
        fam, tf, ss, fp = (m.group(1), m.group(2), m.group(3), bool(m.group(4))) if m else (r["key"], "", "", False)
        pos = r["net"] > 0
        rows.append([f"<b>{esc(fam)}</b> {tf}m {sess_h(ss)}" + (" " + chip("info", "fast-pass") if fp else ""),
                     str(int(float(r["trades"]))),
                     (usd(r["net"], True), f' class="bc {"pb1" if pos else "pb2"}" style="--p:{abs(r["net"]) / mx:.2f}"'),
                     f2(r["pf"]), f2(r["sharpe"])])
    pos = int((w.net > 0).sum())
    o = [f"<p class=lead2>The tester's walk-forward: parameters picked on one month by t-statistic, tested on the next three months, stitched "
         f"out-of-sample, raw P&amp;L at 1 {P.inst} with real costs. <b>{pos} of {len(w)}</b> are positive. Sum {usd(w.net.sum(), True)}, "
         f"median {usd(w.net.median(), True)}. Bars are drawn to scale against the largest absolute result.</p>"]
    o.append(table(["Walk-forward (family, timeframe, session)", "OOS trades", "OOS net", "Profit factor", "Sharpe"], rows, left=(0,), cls="bct"))
    o.append(S("<p class='note'>Profit factor = gross profit / gross loss (above 1 is net positive after costs). Evals can be passed "
               "without a positive expectancy; funded accounts need one, so lean on the positive rows.</p>"))
    return "".join(o)


# ----------------------------------------------------------------------------- 13 Notes for the GC run
def sec13_static(PS):
    nq = PS[0]
    lines = []

    def li(t):
        lines.append(f"<li>{t}</li>")
    ho = nq.has_ho
    lucid_is = g(nq.recs.get("lucid"), "is", "p5") if nq.recs else None
    lucid_ho = g(ho_head(nq.recs.get("lucid")), "p5") if nq.recs else None
    lucid_open = g(nq.recs.get("lucid"), "ho", "intraday", "p5") if nq.recs else None
    o = ["<div class='cols'><div><h4>Reuse</h4><ul>"]
    for t in [
        "Run the tester at 1 contract with all sessions on, then split by session and apply size and daily rules offline. One run serves millions of rule sets exactly.",
        "A day-matched random control (same days, sessions, trade counts, exits and rules) plus a zero-edge null built from random configs run through the same search. Trade-count-only controls overstate edge.",
        "Report every breach model (end-of-day, realised, intraday). The choice moves some results from 70% to near zero.",
        "Freeze a holdout manifest with file and code hashes before opening 2025+, score once, then re-derive independently. NQ: zero mismatches across all finalists.",
        "Independent verify agents found two real bugs this run: a walk-forward look-ahead through a full-window guard, and a Pro daily-limit flag that stayed off. Truncation-test every walk-forward.",
        "Parallel evals on distinct strategies (not in-account portfolios) as the diversifier.",
            ]:
        o.append(f"<li>{t}</li>")
    o.append("</ul><h4>Skip</h4><ul>")
    for t in [
        "In-account portfolios: members add 0 to +3 points and under a one-trade-a-day rule later members never trade.",
        "Asia as a session: the tester's windows are calendar-day, so only 00:00 to 03:00 ET is reachable.",
        "Fast-pass coin-flips at Apex: banned structures, and the open-loss (MAE) rule puts 72 to 85% of trades at the $750 floor on ES.",
        "LucidPro with the $1,200 daily limit: it fails the 60% test on NQ and ES, but it is the one least sensitive to the breach-rule question.",
        "Families the learnings note marks dead on NQ (thin or negative at the screen): mid_fade, gap, pinbar, sweep_rev. Section 5 still shows high pass rates for gap and sweep_rev because a pass rate does not need a positive net.",
            ]:
        o.append(f"<li>{t}</li>")
    o.append("</ul></div><div><h4>Caps and timing</h4><ul>")
    for t in [
        "Tester caps per pilot: 400 screening runs, 3,000 heat-map cells, 15 walk-forwards. NQ used 289 / 1,484 / 15; ES 116 / 932 / 15.",
        "Two tester slots during desk hours (08:00 to 16:15 ET weekdays), four otherwise. Nothing starts 09:20 to 09:35 ET; offline multiprocessing pauses 09:18 to 09:36.",
        "Cost per run: NQ 23 s, ES 41 s for the full 2021-09 to 2024 window; a 20-cell heat-map 244 s (NQ), 320 s (ES). Build the tape cache first (ES: about 97 s).",
        "Keep the Mac on AC with the lid open; hibernation cost about 8.5 hours on the NQ run.",
        "Rescale points-mode stop grids by the instrument's point size (ES points are about 4x smaller than NQ) and recompute costs per contract (ES $29 vs NQ $14 round trip at one contract).",
        "For GC check first: tick value ($10 per 0.10 on GC), the micro (MGC) and its commission, roll dates, nearly 24-hour sessions, and the news calendar.",
            ]:
        o.append(f"<li>{t}</li>")
    o.append("</ul><h4>The breach-rule question</h4>")
    o.append("<p>Every Lucid result depends on one unconfirmed fact. "
             f"{('On NQ the Lucid Flex setup passes about ' + pc(lucid_ho) + ' of holdout attempts if closed balance counts and ' + pc(lucid_open) + ' if open losses count.') if lucid_ho is not None and lucid_open is not None else ''} "
             "Ask in writing and keep the answer next to the sim:</p>"
             "<blockquote>On a LucidFlex or LucidPro 50K account, if a position's unrealised loss takes account equity down to the "
             "Max Loss Limit intraday but the trade recovers and closes above it, is the account breached? Is the MLL tested against "
             "closed (realised) balance only, or against live equity including open P&amp;L? At what time is the end-of-day balance "
             "that sets the trail taken?</blockquote></div></div>")
    return "".join(o)


# ----------------------------------------------------------------------------- 14 Final code and params
def tester_ids(P, fam):
    return (f"draft_pp_es_{fam}", f"pp_es_{fam}") if P.key == "es" else (f"draft_pp_{fam}", f"pp_{fam}")


def spec_for(P, f, cfg, sess, micros):
    """Full parameter spec of a member: from the saved specs, else rebuilt from the candidates table."""
    name = f"{cfg}|{sess}"
    for ff in FIRMS:
        for kind in ("single", "best2", "portfolio"):
            for s_ in g(P.rep(ff, kind), "extras", "specs") or []:
                if s_["config"] == name:
                    return dict(s_, micros=micros or s_.get("micros"))
    c = P.cand
    if c is not None:
        row = c[(c.firm == f) & (c.config.astype(str).str.endswith(f"|{cfg}|{sess}"))]
        if len(row):
            r = row.iloc[0]
            try:
                p = json.loads(r["params"])
            except Exception:
                p = {}
            return {"config": name, "family": r["fam"], "tf": int(r["tf"]), "sess": sess, "micros": micros,
                    "stop_mode": p.get("stop_mode") or ("pts" if num(r.get("fastpass")) == 1 else "atr"),
                    "stop_val": p.get("stop_val"), "tgt_r": p.get("tgt_r"), "exit_bars": p.get("exit_bars"),
                    "trail_atr": p.get("trail_atr"), "max_tr": p.get("max_tr", 3),
                    "family_params": {k: v for k, v in p.items() if k not in ("stop_val", "tgt_r", "stop_mode", "exit_bars", "trail_atr", "max_tr")}}
    return None


def sec14(P):
    if not P.port:
        return nopf(P)
    o = [S("<p class=lead2>Everything needed to rebuild each finalist. Each draft's tester id is <code>draft_&lt;stem&gt;</code> and its file is "
           "<code>~/.homebase/strategies/&lt;stem&gt;.py</code> (NQ stems are <code>pp_&lt;family&gt;</code>, ES stems <code>pp_es_&lt;family&gt;</code>). Tester inputs are the timeframe, "
           "<span class='mono'>sess=all</span> (the session is split offline), and the stop, target and family parameters below. "
           "Sizes and daily rules are applied offline and set in the desk's account rules.</p>"),
         "<h4>Eval finalists: the recommended strategy per firm</h4>"]
    used = set()
    seen = {}
    for f in FIRMS:
        rc = P.recs.get(f) or {}
        for m in rc.get("members", []):
            cfg = m.get("cfg") or str(m.get("name", "")).split("|")[0]
            sp = spec_for(P, f, cfg, m.get("sess"), m.get("micros"))
            if sp:
                ent = seen.setdefault((sp["config"], sp.get("micros")), [sp, {}])
                ent[1].setdefault(f, []).append("rec.")
    rows = []
    for (cfgname, mic), (s_, uses) in seen.items():
        fam = s_["family"]
        used.add(fam)
        did, fpath = tester_ids(P, fam)
        sm = s_.get("stop_mode")
        stop = f"{s_['stop_val']:g} {'ATR' if sm == 'atr' else 'pts'}" if s_.get("stop_val") is not None else "&mdash;"
        tgt = f"{s_['tgt_r']:g}R" if num(s_.get("tgt_r")) else "none"
        ex = []
        if num(s_.get("exit_bars")):
            ex.append(f"exit after {int(s_['exit_bars'])} bars")
        if num(s_.get("trail_atr")):
            ex.append(f"trail {s_['trail_atr']:g} ATR")
        ex.append(f"max {s_.get('max_tr')}/session")
        fp = ", ".join(f"{k}={v}" for k, v in (s_.get("family_params") or {}).items()) or "defaults"
        use = ", ".join(SHORT[f] for f in uses)
        rows.append([f"<code>{esc(fpath)}</code>", esc(cfgname.split("|")[0]),
                     f"{s_['tf']} min", sess_h(s_["sess"]), stop, tgt, ", ".join(ex), esc(fp), str(mic), esc(use)])
    o.append(table(["Draft file stem", "Grid cell", "TF", "Session", "Stop", "Target", "Exit and limits", "Family params", "Micros", "Used by"],
                   rows, left=(0, 1, 3, 4, 5, 6, 7, 9), wide=(6, 9)))
    rr = []
    for f in FIRMS:
        cells = []
        for kind in ("single", "portfolio"):
            r = P.rep(f, kind)
            if kind == "single":
                cells.append(rules_words(P.recs[f]["rules"]) + " (recommended)")
            else:
                cells.append(rules_words(r.get("cell")) if r else "&mdash;")
        rr.append([firm_lbl(f)] + cells)
    o.append("<h4>Eval finalists: daily rules per build (portfolio members are in section 7)</h4>")
    o.append(table(["Firm", "Single", "Portfolio"], rr, left=(0, 1, 2), wide=(1, 2)))
    o.append("<h4>Funded finalists (top pick per variant; the second pick is in section 11)</h4>")
    rows = []
    for v in VARIANTS:
        for k, pk in enumerate((P.picks.get(v) or [])[:1], 1):
            r = pk["row"]
            try:
                p = json.loads(r["params"])
            except Exception:
                p = {}
            fam = r["fam"]
            used.add(fam)
            did, fpath = tester_ids(P, fam)
            sm = p.get("stop_mode") or ("pts" if r.get("pool_group") == "fp" else "atr")
            stop = f"{p['stop_val']:g} {'ATR' if sm == 'atr' else 'pts'}" if "stop_val" in p else "&mdash;"
            tgt = f"{p['tgt_r']:g}R" if num(p.get("tgt_r")) else "none"
            fp = ", ".join(f"{a}={b}" for a, b in p.items() if a not in ("stop_val", "tgt_r", "stop_mode")) or "defaults"
            rules = {"day_take": r.get("day_take"), "day_lock": r.get("day_lock"), "day_stop": r.get("day_stop"), "max_day_tr": r.get("max_day_tr")}
            rows.append([esc(VLONG[v]) if k == 1 else "", f"<code>{esc(fpath)}</code>",
                         esc(r["cid"]), f"{int(r['tf'])} min", sess_h(r["sess"]), stop, tgt, esc(fp), str(int(r["micros"])),
                         rules_words(rules, None, r.get("policy"))])
    if rows:
        o.append(table(["Variant", "Draft file stem", "Grid cell", "TF", "Session", "Stop", "Target", "Family params", "Micros",
                        "Daily rules and payout policy"], rows, left=(0, 1, 2, 4, 5, 6, 7, 9), wide=(0, 9)))
    else:
        o.append(pend("funded finalists not selected yet."))
    P.used_fams = used
    return "".join(o)


def code_block(fams):
    parts = []
    tp = tload(R / "template.py")
    if tp:
        parts.append(f'<details class="code"><summary>Strategy template source, R/template.py ({len(tp.splitlines())} lines; shared by every draft)</summary>'
                     f"<pre><code>{esc(tp)}</code></pre></details>")
    for fam in sorted(fams):
        src = tload(R / "families" / f"{fam}.py")
        if src:
            parts.append(f'<details class="code"><summary>Family entry logic, R/families/{esc(fam)}.py ({len(src.splitlines())} lines)</summary>'
                         f"<pre><code>{esc(src)}</code></pre></details>")
    return ("<h4>Strategy source</h4><p class='note'>gen_drafts.py splices the family file into the template to write each draft "
            "(pp_&lt;family&gt;.py for NQ, pp_es_&lt;family&gt;.py for ES).</p>" + "".join(parts))


# ----------------------------------------------------------------------------- page assembly
LIGHT = """--bg:#f4f5f7;--surface:#ffffff;--ink:#18212d;--ink2:#46515f;--ink3:#6a7585;--rule:#d9dde3;--grid:#e6e9ee;
--accent:#1d4e89;--accent-t:#e1eaf6;--pass:#17703f;--pass-bg:#ddf0e4;--warn:#8f5f00;--warn-bg:#faedc8;
--fail:#b0261d;--fail-bg:#f7dad6;--pend:#4f5b6b;--pend-bg:#e6e9ef;--info:#1d4e89;--info-bg:#e1eaf6;
--s0:#aeb8c6;--s1:#6f93c4;--s2:#1d4e89;--c1:#1d4e89;--c2:#1f8a7d;--c3:#8a6a1f;--c4:#b0566b;--c5:#5d6877;--code:#eceff3;"""
DARK = """--bg:#0f141b;--surface:#161d27;--ink:#e6eaf0;--ink2:#b1bac7;--ink3:#8590a0;--rule:#2b3544;--grid:#212a36;
--accent:#7ea6dc;--accent-t:#1b2a42;--pass:#62c88b;--pass-bg:#16301f;--warn:#e2b34a;--warn-bg:#352a0d;
--fail:#f08c84;--fail-bg:#3b1a18;--pend:#a0abba;--pend-bg:#232c39;--info:#7ea6dc;--info-bg:#1b2a42;
--s0:#4b5869;--s1:#4f79ae;--s2:#7ea6dc;--c1:#7ea6dc;--c2:#4fc0b2;--c3:#d0a94c;--c4:#e08ca0;--c5:#9aa5b5;--code:#1b222d;"""

CSS_BASE = r"""
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 "IBM Plex Sans",system-ui,-apple-system,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;font-variant-numeric:tabular-nums}
.rpt{max-width:1180px;margin-inline:auto;padding-inline:16px;padding-block:20px 72px}
@media(min-width:760px){.rpt{padding-inline:28px}}
h1,h2,h3,h4,h5{text-wrap:balance;line-height:1.25;margin:0;font-weight:600}
h1{font-size:clamp(22px,4.6vw,30px);letter-spacing:-.01em}
h2{font-size:clamp(19px,3.4vw,23px);margin-top:52px;padding-top:16px;border-top:2px solid var(--ink);display:flex;gap:12px;align-items:baseline}
h3.mh{font-size:13px;letter-spacing:.08em;text-transform:uppercase;color:var(--accent);margin:26px 0 4px;font-weight:600}
h4{font-size:15px;margin:22px 0 6px}
h5{font-size:14px;margin:18px 0 4px;color:var(--ink2)}
.n{font:500 13px "IBM Plex Mono",ui-monospace,Menlo,Consolas,monospace;color:var(--accent)}
p{margin:6px 0 10px;max-width:78ch}
.lead,.lead2{color:var(--ink2);max-width:78ch}
.eyebrow{font:500 12px "IBM Plex Mono",ui-monospace,Menlo,monospace;color:var(--ink3);letter-spacing:.04em;margin:0 0 8px}
.sub{font-size:16px;color:var(--ink2);margin:10px 0 0}
.mono,code,pre{font-family:"IBM Plex Mono",ui-monospace,Menlo,Consolas,monospace}
code.sm,.sm{font-size:11px;color:var(--ink3)}
.note{font-size:12.5px;color:var(--ink2)}
var{font-style:normal;font-size:11.5px;color:var(--ink3);white-space:nowrap}
small{font-size:11px;color:var(--ink3);display:block;font-weight:400}
a{color:var(--accent)}
.bar{position:sticky;top:0;z-index:5;background:var(--bg);padding-block:8px;margin-top:14px;border-bottom:1px solid var(--rule)}
.seg{display:flex;gap:0;margin-bottom:6px}
.seg label{font:600 13px "IBM Plex Sans",system-ui,sans-serif;padding:6px 16px;border:1px solid var(--rule);background:var(--surface);color:var(--ink2);cursor:pointer;margin-left:-1px}
.seg label:first-child{border-radius:4px 0 0 4px;margin-left:0}.seg label:last-child{border-radius:0 4px 4px 0}
.mkr{position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%);white-space:nowrap}
#m-nq:checked~.bar label[for=m-nq],#m-es:checked~.bar label[for=m-es],#m-both:checked~.bar label[for=m-both]{background:var(--accent);color:var(--surface);border-color:var(--accent)}
.mkr:focus-visible~.bar .seg{outline:2px solid var(--accent);outline-offset:2px}
.rpt:has(#m-nq:checked) .mk-es{display:none}
.rpt:has(#m-es:checked) .mk-nq{display:none}
nav.nv{display:flex;gap:4px;overflow-x:auto;padding-bottom:2px}
nav.nv a{flex:none;font:500 12px "IBM Plex Mono",ui-monospace,monospace;text-decoration:none;color:var(--ink2);padding:3px 7px;border:1px solid var(--rule);border-radius:3px;background:var(--surface)}
nav.nv a:hover{border-color:var(--accent);color:var(--accent)}
.tw{overflow-x:auto;margin:8px 0 16px;border-top:1px solid var(--rule);border-bottom:1px solid var(--rule);background:var(--surface)}
table{border-collapse:collapse;width:100%;font-size:12.5px}
th,td{padding:5px 9px;text-align:right;white-space:nowrap;vertical-align:top;border-bottom:1px solid var(--grid)}
th{font-weight:600;color:var(--ink2);background:var(--bg);border-bottom:1px solid var(--rule);vertical-align:bottom;white-space:normal;min-width:62px}
th.l,td.l,th.lw{text-align:left}
td.w,td.lw{white-space:normal;min-width:150px}
td.lw,th.lw{text-align:left}
th.w{min-width:200px}
tr:last-child td{border-bottom:0}
.hmt td{line-height:1.25}
.h1{background:color-mix(in srgb,var(--accent) 8%,var(--surface))}.h2{background:color-mix(in srgb,var(--accent) 16%,var(--surface))}.h3{background:color-mix(in srgb,var(--accent) 24%,var(--surface))}.h4{background:color-mix(in srgb,var(--accent) 32%,var(--surface))}.h5{background:color-mix(in srgb,var(--accent) 40%,var(--surface))}
.n1{background:color-mix(in srgb,var(--fail) 8%,var(--surface))}.n2{background:color-mix(in srgb,var(--fail) 16%,var(--surface))}.n3{background:color-mix(in srgb,var(--fail) 24%,var(--surface))}.n4{background:color-mix(in srgb,var(--fail) 32%,var(--surface))}.n5{background:color-mix(in srgb,var(--fail) 40%,var(--surface))}
.hmt td b{font-weight:600}
.cm{max-width:300px}.cm td,.cm th{text-align:center}
.bct td.bc{text-align:left;min-width:64px;background:linear-gradient(90deg,var(--bg-bar) calc(var(--p)*100%),transparent 0)}
.bct td.pb1{--bg-bar:var(--accent-t)}.bct td.pb2{--bg-bar:var(--fail-bg)}
b.ok,b.warn,b.bad,b.pend,b.info{display:inline-block;font:600 10.5px/1 "IBM Plex Sans",system-ui,sans-serif;letter-spacing:.03em;padding:3px 6px;border-radius:3px;white-space:nowrap;vertical-align:1px}
b.ok{color:var(--pass);background:var(--pass-bg)}b.warn{color:var(--warn);background:var(--warn-bg)}
b.bad{color:var(--fail);background:var(--fail-bg)}b.pend{color:var(--pend);background:var(--pend-bg)}
b.info{color:var(--info);background:var(--info-bg)}
.pb{border:1px dashed var(--ink3);padding:8px 12px;color:var(--ink2);font-size:13.5px;background:var(--surface);margin:10px 0}
.risk{border:1px solid var(--fail);border-left:5px solid var(--fail);background:var(--surface);padding:6px 16px 8px;margin:22px 0}
.risk h4{margin-top:10px;color:var(--fail)}
.callout{border-left:4px solid var(--warn);background:var(--surface);padding:8px 14px;margin:12px 0;font-size:14px}
dl.kv{margin:8px 0 14px;display:grid;grid-template-columns:minmax(120px,210px) 1fr;gap:0;border-top:1px solid var(--rule)}
dl.kv dt,dl.kv dd{margin:0;padding:7px 10px 7px 0;border-bottom:1px solid var(--grid)}
dl.kv dt{font-weight:600;font-size:13.5px}
dl.kv dd{font-size:13.5px;color:var(--ink2)}
@media(max-width:560px){dl.kv{grid-template-columns:1fr}dl.kv dt{border-bottom:0;padding-bottom:0}}
details.terms{margin:20px 0 0;border:1px solid var(--rule);background:var(--surface);padding:8px 14px}
details summary{cursor:pointer;font-weight:600;font-size:14px}
details.code{margin:8px 0;border:1px solid var(--rule);background:var(--surface);padding:8px 12px}
pre{margin:8px 0 0;background:var(--code);padding:10px 12px;overflow-x:auto;font-size:11.5px;line-height:1.45;max-height:560px;overflow-y:auto}
pre code{white-space:pre}
.cols{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:4px 36px}
.cols ul{margin:4px 0 8px;padding-left:18px}.cols li{margin:5px 0;font-size:14px;max-width:70ch}
blockquote{margin:8px 0;padding:8px 14px;border-left:3px solid var(--accent);background:var(--surface);font-size:13.5px;color:var(--ink2)}
.cg{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:8px 28px;margin:8px 0}
.fg{margin:0}.fg figcaption{font-weight:600;font-size:13px;margin-bottom:2px}
ul.mem{list-style:none;padding:0;margin:4px 0;font-size:12.5px;color:var(--ink2)}ul.mem li{margin:1px 0}
.ch{width:100%;max-width:520px;height:auto;display:block;overflow:visible}
.lg{display:flex;flex-wrap:wrap;gap:4px 16px;font-size:12px;color:var(--ink2);margin:8px 0 2px}
.lg span{display:inline-flex;align-items:center;gap:6px}
.sw{display:inline-block;width:11px;height:11px;border-radius:2px}
.sw.s0{background:var(--s0)}.sw.s1{background:var(--s1)}.sw.s2{background:var(--s2)}
.sw.l0{background:var(--c1)}.sw.l1{background:var(--c2)}.sw.l2{background:var(--c3)}.sw.l3{background:var(--c4)}.sw.l4{background:var(--c5)}
.t{font:10px "IBM Plex Sans",system-ui,sans-serif;fill:var(--ink2)}.t3{font:9.5px "IBM Plex Sans",system-ui,sans-serif;fill:var(--ink3)}
.tb{font:500 10.5px "IBM Plex Sans",system-ui,sans-serif;fill:var(--ink)}.v{font:9.5px "IBM Plex Mono",ui-monospace,monospace;fill:var(--ink)}
.tr{font:500 9.5px "IBM Plex Sans",system-ui,sans-serif;fill:var(--accent)}.tl{font:500 9.5px "IBM Plex Sans",system-ui,sans-serif}
.ta-m{text-anchor:middle}.ta-e{text-anchor:end}
.gl{stroke:var(--grid);stroke-width:1}.ax{stroke:var(--ink3);stroke-width:1}.ref{stroke:var(--accent);stroke-width:1;stroke-dasharray:3 3}
.s0{fill:var(--s0)}.s1{fill:var(--s1)}.s2{fill:var(--s2)}
.ln{fill:none;stroke-width:1.8;stroke-linejoin:round}
.ln.l0{stroke:var(--c1)}.ln.l1{stroke:var(--c2)}.ln.l2{stroke:var(--c3)}.ln.l3{stroke:var(--c4)}.ln.l4{stroke:var(--c5)}
.pt.l0{fill:var(--c1)}.pt.l1{fill:var(--c2)}.pt.l2{fill:var(--c3)}.pt.l3{fill:var(--c4)}.pt.l4{fill:var(--c5)}
.tl.l0{fill:var(--c1)}.tl.l1{fill:var(--c2)}.tl.l2{fill:var(--c3)}.tl.l3{fill:var(--c4)}.tl.l4{fill:var(--c5)}
.ln.d1{stroke-dasharray:6 3}.ln.d2{stroke-dasharray:2 2}.ln.d3{stroke-dasharray:7 2 1 2}.ln.d4{stroke-dasharray:1 3}
.hp{fill:color-mix(in srgb,var(--accent) calc(var(--v)*85%),var(--surface))}.hn{fill:color-mix(in srgb,var(--fail) calc(var(--v)*85%),var(--surface))}
.chips{display:flex;flex-wrap:wrap;gap:6px 14px;margin:14px 0 0;font-size:13px;color:var(--ink2)}
.chips span{display:inline-flex;flex-wrap:wrap;gap:6px;align-items:center}.chips var{white-space:normal}footer{margin-top:56px;padding-top:12px;border-top:1px solid var(--rule);font-size:12px;color:var(--ink3)}
"""

CSS_PRINT = r"""
@page{size:A4 landscape;margin:11mm 10mm}
body{background:var(--bg);font-size:12px}
.rpt{max-width:none;padding:0}
section{break-before:page}section:first-of-type{break-before:auto}
h2{margin-top:0;break-after:avoid}h3.mh,h4,h5{break-after:avoid}
figure,.risk,.callout,details,.kv,tr{break-inside:avoid}
.tw{overflow:visible}
body{background:var(--surface)}
th,td{padding:3px 6px;font-size:10.5px;white-space:normal}
td.w{min-width:120px}
.cg,pre{max-height:none;overflow:visible;font-size:8.5px;white-space:pre-wrap}
.bar,nav.nv{display:none}
.mk{margin-bottom:6px}
.mk-es{break-before:page}
.ch{max-width:430px}
"""

IMPORT = '@import url("https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&display=swap");'


def build_css(print_variant=False):
    css = IMPORT + ":root{" + LIGHT + "}"
    if not print_variant:
        css += ("@media (prefers-color-scheme: dark){:root:not([data-theme=\"light\"]){" + DARK + "color-scheme:dark}}"
                ":root[data-theme=\"dark\"]{" + DARK + "color-scheme:dark}")
    css += CSS_BASE
    if print_variant:
        css += CSS_PRINT
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    css = re.sub(r"\s*\n\s*", "", css)
    css = re.sub(r"\s*([{};,>])\s*", r"\1", css)
    css = re.sub(r":\s+", ":", css)
    return css


SECTIONS = [
    (1, "Verdict", "Can a strategy pass a 50K eval within 5 trading days at least 60% of the time? The test is run three ways: "
                   "on the search data, on a walk-forward, and on 2025+ data that was never used to choose anything."),
    (2, "Firm rules and zero-edge baselines", "What each firm's rules are as modelled, and what random entries achieve by tuning daily rules alone."),
    (3, "Firm comparison", "Speed, bust risk, cost per funded account, funded payout and value per eval purchase, side by side."),
    (4, "Leaderboard", "Best searched configs per firm, with the evidence flags that matter."),
    (5, "Breakdowns", "Which families, timeframes, sessions and exit styles carry the pass rate."),
    (6, "Correlation of finalist members", "Do the strategies in a portfolio win and lose on the same days?"),
    (7, "Portfolio vs single, and multiple accounts", "More strategies in one account, or more accounts?"),
    (8, "Pass vs risk", "What changes when the position size is cut or raised."),
    (9, "Day 1 to 5", "On which day attempts end, pass or bust."),
    (10, "News vs non-news", "Does a CPI, jobs or FOMC day in the window change the outcome?"),
    (11, "Funded accounts", "Payout odds, size and speed once an eval is passed."),
    (12, "Homebase walk-forwards", "Fifteen parameter walk-forwards per market on the tester: is there a positive expectancy?"),
    (13, "Notes for the GC run", "Lessons from this run and the learnings note: what to reuse, what to skip, limits and timing, and the open rule question."),
    (14, "Final code and parameters", "Full parameter sets and strategy source for every finalist."),
]


def render_section(n, PS, print_variant=False):
    title, lead = next((t, l) for k, t, l in SECTIONS if k == n)
    fn = {1: sec1, 2: sec2, 3: sec3, 4: sec4, 5: sec5, 6: sec6, 7: sec7, 8: sec8, 9: sec9, 10: sec10, 11: sec11, 12: sec12, 13: None,
          14: sec14}[n]
    parts = [f'<section id="s{n}"><h2><span class="n">{n:02d}</span>{esc(title)}</h2><p class="lead">{esc(lead)}</p>']
    first = next((p for p in PS if p.port), None)
    if n == 2:
        parts.append(sec2_static(first))
    if n == 1:
        parts.append(terms())
    if n == 5:
        parts.append(fam_gloss_block())
    if n == 8:
        parts.append(legend([(f"l{i}", SHORT[f]) for i, f in enumerate(FIRMS)]))
    if n == 13:
        parts.append(sec13_static(PS))
    if fn:
        bodies = []
        for P in PS:
            try:
                body = fn(P)
            except Exception as e:  # keep the report building when one market's file set is partial
                import traceback
                traceback.print_exc()
                body = pend(f"section could not render from the files that exist today ({type(e).__name__}: {e}).")
            bodies.append((P, body))
        pat = re.compile(r"<!--S-->(.*?)<!--/S-->", re.S)
        shared = next((pat.findall(b) for _, b in bodies if pat.search(b)), [])
        parts.append("".join(shared))
        for P, body in bodies:
            parts.append(f'<div class="mk mk-{P.key}"><h3 class="mh">{esc(P.label)}</h3>{pat.sub("", body)}</div>')
    if n == 14:
        fams = set()
        for P in PS:
            fams |= getattr(P, "used_fams", set())
        parts.append(code_block(fams))
    parts.append("</section>")
    return "".join(parts)


def headline(PS):
    bits = []
    for P in PS:
        if not P.port:
            bits.append(f"{P.key.upper()}: no portfolio results yet.")
            continue
        best = max(((g(P.recs[f], "is", "p5") or 0, f) for f in FIRMS), default=(0, None))
        if P.has_ho:
            passed = [f for f in FIRMS if (num(ho_head(P.recs[f]).get("p5")) or 0) >= THRESH]
            frag = [f for f in passed if (num(g(P.recs[f], "ho", "intraday", "p5")) or 0) < THRESH and P.recs[f]["primary"] != "intraday"]
            bits.append(f"<b>{P.key.upper()}</b>: {len(passed)} of 5 setups meet the 60% test on the 2025+ holdout "
                        f"({', '.join(SHORT[f] for f in passed) or 'none'})"
                        + (f", but only if Lucid counts closed balance: under open-loss breach they drop to {pc(max(g(P.recs[f], 'ho', 'intraday', 'p5') or 0 for f in frag))} or less." if frag else "."))
        else:
            bits.append(f"<b>{P.key.upper()}</b>: best in-sample P(pass in 5 days) is {pc(best[0])} ({SHORT.get(best[1], '')}); "
                        f"{'none reach' if best[0] < THRESH else 'some reach'} 60%. Holdout pending.")
    return " ".join(bits)


def status_chips(PS):
    out = []
    for P in PS:
        out.append(f'<span><b class="mono">{P.key.upper()}</b> '
                   f'{chip("ok", "holdout scored") if P.has_ho else chip("pend", "holdout pending")} '
                   f'{chip("ok", "independently verified") if P.verified else chip("pend", "verification pending")} '
                   f'<span class="ci">files as of {esc(P.mtime())}</span></span>')
    return '<div class="chips">' + "".join(out) + "</div>"


def build_body(PS, print_variant=False):
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    NAVL = ["Verdict", "Rules", "Compare", "Leaders", "Breakdown", "Corr.", "Portfolio", "Risk", "Days", "News", "Funded", "WF", "GC notes", "Code"]
    nav = "".join(f'<a href="#s{n}">{n:02d} {NAVL[n - 1]}</a>' for n, t, _ in SECTIONS)
    head = (f'<div class="hd"><p class="eyebrow">PROP-FIRM EVAL DESK &middot; RESEARCH REPORT &middot; GENERATED {now}</p>'
            f"<h1>NQ and ES: passing a 50K prop eval in five days</h1>"
            f'<p class="sub">{headline(PS)}</p>{status_chips(PS)}</div>')
    if print_variant:
        bar = ""
        radios = ""
    else:
        radios = ('<input class="mkr" type="radio" name="mk" id="m-nq" checked aria-label="Show NQ"><input class="mkr" type="radio" name="mk" id="m-es" aria-label="Show ES">'
                  '<input class="mkr" type="radio" name="mk" id="m-both" aria-label="Show both">')
        bar = (f'<div class="bar"><div class="seg" role="group" aria-label="Market"><label for="m-nq">NQ</label><label for="m-es">ES</label>'
               f'<label for="m-both">Both</label></div><nav class="nv" aria-label="Sections">{nav}</nav></div>')
    secs = "".join(render_section(n, PS, print_variant) for n, _, _ in SECTIONS)
    foot = ("<footer>Built by research/prop-portfolio/2026-09-29/build_report.py from frozen outputs in the NQ and ES pilot folders. "
            "No backtest was run and nothing was re-scored. Fees are assumptions unless marked from you. Apex rules are UNCONFIRMED. "
            "Research, not investment advice.</footer>")
    return f'<div class="rpt">{radios}{head}{bar}<main>{secs}</main>{foot}</div>'


ENT = {"&mdash;": "\u2014", "&middot;": "\u00b7", "&ge;": "\u2265", "&le;": "\u2264", "&times;": "\u00d7", "&divide;": "\u00f7",
       "&ldquo;": "\u201c", "&rdquo;": "\u201d", "&nbsp;": "\u00a0"}


def squeeze(h):
    for a, b in ENT.items():
        h = h.replace(a, b)
    h = re.sub(r'<b class="c (\w+)">', r"<b class=\1>", h)
    h = re.sub(r'<span class="ci">(.*?)</span>', r"<var>\1</var>", h)
    h = re.sub(r'<span class="mono sm">(.*?)</span>', r"<code class=sm>\1</code>", h)
    h = re.sub(r'<span class="mono">(.*?)</span>', r"<code>\1</code>", h)
    h = re.sub(r' class="([\w-]+)"(?!/)', r" class=\1", h)
    h = re.sub(r' id="(\w+)"', r" id=\1", h)
    return h


def page_count(pdf):
    try:
        b = Path(pdf).read_bytes()
        return len(re.findall(rb"/Type\s*/Page(?![a-zA-Z])", b))
    except Exception:
        return None


def make_pdf(print_html: Path, pdf: Path):
    if os.path.exists(CHROME):
        for extra in (["--no-sandbox"], []):
            cmd = [CHROME, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", "--virtual-time-budget=20000"] + extra + [
                f"--print-to-pdf={pdf}", f"file://{print_html}"]
            try:
                if pdf.exists():
                    pdf.unlink()
                subprocess.run(cmd, check=False, capture_output=True, timeout=180)
            except Exception as e:
                print("chrome failed:", e, file=sys.stderr)
            if pdf.exists() and pdf.stat().st_size > 5000:
                return "chrome"
    # matplotlib fallback: text-only summary pages
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.backends.backend_pdf import PdfPages
        txt = re.sub(r"<[^>]+>", " ", print_html.read_text())
        txt = html.unescape(re.sub(r"\s+", " ", txt))
        with PdfPages(pdf) as pp:
            for i in range(0, len(txt), 3200):
                fig = plt.figure(figsize=(11.7, 8.3))
                fig.text(0.04, 0.96, txt[i:i + 3200], va="top", fontsize=7, wrap=True)
                pp.savefig(fig)
                plt.close(fig)
        return "matplotlib"
    except Exception as e:
        print("matplotlib fallback failed:", e, file=sys.stderr)
        return None


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    PS = [Pilot("nq", "NQ (E-mini Nasdaq-100)", R, "NQ", "NQ"), Pilot("es", "ES (E-mini S&P 500)", RE, "ES", "ES")]
    for P in PS:
        prep(P)
    web_body = squeeze(build_body(PS, False))
    index = ("<title>NQ ES Prop Pilot</title>\n<style>" + build_css(False) + "</style>\n" + web_body + "\n")
    (OUT / "index.html").write_text(index)
    print_doc = ('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
                 "<title>NQ ES Prop Pilot</title><style>" + build_css(True) + "</style></head><body>" + squeeze(build_body(PS, True)) + "</body></html>")
    ph = OUT / "print.html"
    ph.write_text(print_doc)
    pdf = OUT / "NQ_ES_Prop_Pilot.pdf"
    how = make_pdf(ph, pdf)
    size = (OUT / "index.html").stat().st_size
    print(f"index.html {size / 1024:.1f} KB ({'OK' if size <= 150 * 1024 else 'OVER 150 KB'})")
    print(f"print.html {ph.stat().st_size / 1024:.1f} KB")
    if pdf.exists():
        print(f"PDF via {how}: {pdf.stat().st_size / 1024:.0f} KB, {page_count(pdf)} pages")
    for P in PS:
        print(P.key, "holdout" if P.has_ho else "holdout PENDING", "verified" if P.verified else "verification PENDING",
              {k: v for k, v in P.files.items() if not v})


if __name__ == "__main__":
    main()
