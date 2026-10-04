"""Splice template.py + families/<fam>.py -> ~/.homebase/strategies/pp_<fam>.py, then confirm through the
chart service that every draft loads. Also (re)builds news_days.csv. Usage: gen_drafts.py [fam ...]"""
import ast
import collections
import csv
import datetime as dt
import importlib.util
import json
import os
import re
import sys
from pathlib import Path

R = Path(__file__).resolve().parent
REPO = Path.home() / "ramos-quant-homebase"
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(R))
from homebase import draftstore                      # noqa: E402  (reads/writes text only)
from homebase.claude_mcp.client import Client         # noqa: E402
import pilot as PL                                     # noqa: E402  (--pilot es / PP_PILOT=es: root ES, pp_es_<fam>)

FF = Path.home() / "ONYX TRADING/research/data/ff_usd_red_raw.txt"
FAMS = ["orb", "straddle", "donchian", "squeeze", "ema_ribbon", "tema_slope", "ema_pullback", "supertrend",
        "rsi2", "vwap_band", "vwap_z", "vwap_flip", "pinbar", "sweep_rev", "ib", "gap", "tod_drift", "random",
        "lon_break", "first_bar_mom", "mid_fade"]
KEYS = ("key", "label", "type", "default", "min", "max", "step", "choices")
C = ("choice", None, None, None)
COMMON = [
    ("tf", "Signal timeframe (min)", "choice", "5", None, None, None, ("1", "5", "15", "30")),
    ("sess", "Session", "choice", "all", None, None, None, ("all", "asia", "london", "nyam", "mid", "pm")),
    ("dir", "Direction", "choice", "both", None, None, None, ("both", "long", "short")),
    ("stop_mode", "Stop mode", "choice", "atr", None, None, None, ("atr", "pts", "struct")),
    ("stop_val", "Stop (x ATR, or points)", "float", 1.5, 0.1, 1000, 0.05),
    ("tgt_r", "Target (x stop, 0 = none)", "float", 2.0, 0, 20, 0.25),
    ("trail_atr", "Close-trail (x ATR, 0 = off)", "float", 0.0, 0, 10, 0.25),
    ("exit_bars", "Exit after N tf bars (0 = off)", "int", 0, 0, 500, 1),
    ("max_tr", "Max entries per session", "int", 3, 1, 20, 1),
    ("f_trend", "Filter: EMA50 slope", "choice", "off", None, None, None, ("off", "with", "against")),
    ("f_vwap", "Filter: session VWAP side", "choice", "off", None, None, None, ("off", "with", "against")),
]


def build_news():
    tags = {"CPI m/m": "CPI", "Core CPI m/m": "CPI", "CPI y/y": "CPI", "Core CPI y/y": "CPI",   # Jan 2021 is y/y only
            "Non-Farm Employment Change": "NFP", "FOMC Statement": "FOMC",
            "Federal Funds Rate": "FOMC"}                                 # ADP is a different event name
    days = collections.defaultdict(set)
    for e in re.split(r";;|\n", FF.read_text()):
        p = e.strip().split("|")
        if len(p) == 3 and p[2] in tags:
            days[dt.datetime.strptime(p[0], "%b %d, %Y").date()].add(tags[p[2]])
    if PL.NAME == "nq":                                              # other pilots reuse R/news_days.csv as is
        with open(R / "news_days.csv", "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["date", "tags"])
            for d in sorted(days):
                w.writerow([d.isoformat(), "|".join(sorted(days[d]))])
    n = collections.Counter((d.year, t) for d, v in days.items() for t in v)
    print("news_days.csv: %d days | %s" % (len(days), "  ".join(
        "%d %s" % (y, " ".join("%s=%d" % (t, n[(y, t)]) for t in ("CPI", "NFP", "FOMC"))) for y in range(2021, 2027))))
    # release time: CPI/NFP 08:30 ("N"), FOMC statement 14:00 ("F"); the straddle brackets each pre-release
    return {d.isoformat(): ("N" if days[d] & {"CPI", "NFP"} else "") + ("F" if "FOMC" in days[d] else "")
            for d in sorted(days) if 2021 <= d.year <= 2026}


def build_rolls():
    """Session dates whose front contract (most ticks, as tape.pick) differs from the previous session's. The
    prior daily bar is then the OLD contract, so prior-day levels are dropped. Covers every archive year (2021 ... latest): the 2025+
    dates were added for the holdout (2026-09-30); roll detection is sequential, so the 2021-24 list is unchanged by them."""
    best = {}
    for m in (Path.home() / "futures_ticks" / PL.ROOT).glob("20[2-9][0-9]/*.json"):
        try:
            n = int(json.loads(m.read_text())["ticks"])
        except (OSError, ValueError, KeyError):
            continue
        d, c = m.name[:10], m.name[11:-5]
        if d not in best or n > best[d][1]:
            best[d] = (c, n)
    out, prev = [], None
    for d in sorted(best):
        if prev and best[d][0] != prev:
            out.append(d)
        prev = best[d][0]
    return out


def load(fam):
    p = R / "families" / f"{fam}.py"
    spec = importlib.util.spec_from_file_location(f"fam_{fam}", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    src = p.read_text()
    cls = next(n for n in ast.parse(src).body if isinstance(n, ast.ClassDef) and n.name == "Fam")
    body = "\n".join(src.splitlines()[cls.body[0].lineno - 1:cls.end_lineno])
    return m, body


def inp(t):
    d = dict(zip(KEYS, t))
    args = [d[k] for k in KEYS[:7]]
    if d.get("choices"):
        args.append(tuple(d["choices"]))
    return "            Input(" + ", ".join(repr(a) for a in args) + "),"


def gen(fam, tpl, news, rolls):
    m, body = load(fam)
    over = getattr(m, "OVERRIDES", {})
    rows = []
    for t in COMMON:
        d = dict(zip(KEYS, t))
        d.update(over.get(d["key"], {}))
        rows.append(tuple(d.get(k) for k in KEYS))
    rows += [tuple(t) + (None,) * (8 - len(t)) if len(t) < 8 else tuple(t) for t in m.INPUTS]
    keys = [r[0] for r in rows]
    assert len(set(keys)) == len(keys), f"{fam}: duplicate input keys"
    assert '"""' not in m.__doc__
    wrap = lambda t: "\n".join(re.findall(r".{1,100}(?:, |$)", t))
    consts = "# contract-roll session dates 2021-2024 (extend before any 2025+ run)\n" + wrap(
        "ROLLS = frozenset((" + ", ".join(repr(d) for d in rolls) + ",))")
    if getattr(m, "USES_NEWS", False):
        consts += "\n# CPI/NFP (N, 08:30) and FOMC (F, 14:00) days 2021-2026 (news_days.csv)\n" + wrap(
            "NEWS = {" + ", ".join("%r: %r" % kv for kv in news.items()) + "}")
    cname = "PP" + ("" if PL.NAME == "nq" else PL.NAME.capitalize()) + "".join(w.capitalize() for w in fam.split("_"))
    out = (tpl.replace("#@@IMPORTS", "\n".join(f"import {i}" for i in getattr(m, "IMPORTS", [])))
              .replace("#@@CONSTS", consts)
              .replace("#@@INPUTS", "\n".join(inp(r) for r in rows))
              .replace("#@@FAM", body)
              .replace("__DOC__", " ".join(m.__doc__.split()))
              .replace("__CLASS__", cname).replace("__NAME__", f"{PL.PREFIX}{fam}").replace("__ROOT__", PL.ROOT)
              .replace("__TITLE__", m.TITLE + ("" if PL.NAME == "nq" else f" [{PL.ROOT}]")).replace("__FAM__", fam))
    return out


def over_(fam):
    return getattr(load(fam)[0], "OVERRIDES", {})


def main(argv):
    argv = PL.strip_flags(argv)                                  # drop --pilot X / --dir D (read by pilot.py at import)
    news, rolls = build_news(), build_rolls()
    print("rolls:", len(rolls))
    tpl = (R / "template.py").read_text()
    fams = argv or FAMS
    names, info = [], {}
    for fam in fams:
        code = gen(fam, tpl, news, rolls)
        meta = draftstore.static_meta(code)                       # ValueError if the catalog can't read it
        draftstore.write(f"{PL.PREFIX}{fam}", code)
        names.append(f"draft_{PL.PREFIX}{fam}")
        info[fam] = [[i["key"], i["type"], i["default"], i["choices"] or [i["min"], i["max"]]]
                     for i in meta["inputs"] if i["key"] not in {c[0] for c in COMMON} or i["key"] in over_(fam)]
        print(f"{PL.PREFIX}{fam}: {len(code):,} B, {len(meta['inputs'])} inputs")
    if not argv:
        (PL.DIR / "family_inputs.json").write_text(json.dumps({"common": [[d["key"], d["default"], d.get("choices") or [d["min"], d["max"]]] for d in map(lambda c: dict(zip(KEYS, c)), COMMON)], **info}, separators=(",", ":")))
    cat = {s.get("id"): s for s in Client().get("/api/tester/strategies")}
    bad = [n for n in names if n not in cat or cat[n].get("error")]
    for n in bad:
        print("DOES NOT LOAD:", n, (cat.get(n) or {}).get("error", "missing from catalog"))
    print("tester catalog: %d/%d drafts load" % (len(names) - len(bad), len(names)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
