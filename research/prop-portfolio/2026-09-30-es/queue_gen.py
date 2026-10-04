#!/usr/bin/env python3
"""Builds the ES pilot's job lines (same design as NQ): smoke | calib | screen | ctrl  ->  stdout (one JSON per line).
Submit with:  hb.py submit <file>   (lines carry "pilot": "es"; hb.py routes them to RE/queue.jsonl)."""
import json
import sys

FAMS = ["orb", "straddle", "donchian", "squeeze", "ema_ribbon", "tema_slope", "ema_pullback", "supertrend", "rsi2", "vwap_band",
        "vwap_z", "vwap_flip", "pinbar", "sweep_rev", "ib", "gap", "tod_drift", "lon_break", "first_bar_mom", "mid_fade"]   # 20 (random = control)
TFS = ["1", "5", "15", "30"]
PR = "lucid-flex-50k@2026-09-27"
RNG = {"preset": "2021-2024"}
TOD = {"tgt_r": 0.0, "exit_bars": 6, "max_tr": 1}


def S(f):
    return f"draft_pp_es_{f}"


def run(key, stage, strat, inputs, rng=RNG):
    return {"key": key, "kind": "run", "stage": stage, "pilot": "es", "strategy": strat, "inputs": inputs, "range": rng,
            "costs": {"qty": 1}, "prop_rules": PR}


def smoke():
    r = {"preset": "custom", "start": "2024-03-04", "end": "2024-03-15"}
    return [run(f"smoke-{f}", "calib", S(f), {"sess": "all", "tf": "5"}, r) for f in FAMS + ["random"]]


def calib():
    return [run("calib-full-ema_pullback-tf5", "calib", S("ema_pullback"), {"tf": "5", "sess": "all"}),
            {"key": "calib-grid20-orb", "kind": "grid", "stage": "calib", "pilot": "es", "strategy": S("orb"), "inputs": {"sess": "all"},
             "axes": [{"key": "tf", "values": ["1", "5", "15", "30"]}, {"key": "stop_val", "values": [0.5, 1.0, 1.5, 2.0, 3.0]}],
             "max_cells": 20, "range": RNG, "costs": {"qty": 1}, "prop_rules": PR}]


def screen():
    return [run(f"screen-{f}-tf{t}", "screen", S(f), {"tf": t, "sess": "all"}) for f in FAMS for t in TFS]


def ctrl():
    out = []
    for t in TFS:
        for s in (1, 2, 3):
            out.append(run(f"ctrl-random-tf{t}-s{s}", "ctrl", S("random"), {"tf": t, "sess": "all", "p_entry": 0.1, "seed": s}))
        out.append(run(f"ctrl-randomtod-tf{t}-s1", "ctrl", S("random"), {"tf": t, "sess": "all", "p_entry": 0.1, "seed": 1, **TOD}))
    for t in TFS:
        for s in (11, 12, 13):
            out.append(run(f"ctrl2-random-tf{t}-s{s}", "ctrl", S("random"), {"tf": t, "sess": "all", "p_entry": 0.5, "seed": s}))
        for s in (11, 12):
            out.append(run(f"ctrl2-randomtod-tf{t}-s{s}", "ctrl", S("random"), {"tf": t, "sess": "all", "p_entry": 0.5, "seed": s, **TOD}))
    return out


# ---- tuning (stage sizing / ctrl): heat-maps on the top family x tf + fast-pass grids + random exit-profile controls ----------------
# Same axes pattern as NQ tune1/tune2: family param x stop_val {1,2,3} x tgt_r {0.5,1,2,3} (ATR multiples: unit-free, same as NQ).
FAMAX = {"orb": ("or_min", ["5", "15", "30"]), "straddle": ("off_atr", [0.25, 0.5, 1.0]), "donchian": ("n", [10, 20, 40]),
         "squeeze": ("sq_type", ["bbkc", "nr7", "inside"]), "ema_ribbon": ("max_tr", [1, 3]), "tema_slope": ("n", [10, 20, 40]),
         "ema_pullback": ("max_tr", [1, 3]), "supertrend": ("max_tr", [1, 3]), "rsi2": ("th", [5.0, 10.0, 15.0]),
         "vwap_band": ("band", [1.5, 2.0, 2.5, 3.0]), "vwap_z": ("zth", [1.5, 2.0, 2.5, 3.0]), "vwap_flip": ("hold", [1, 2, 3]),
         "pinbar": ("wick", [0.6, 0.667, 0.75]), "sweep_rev": ("levels", ["both", "pd", "on"]), "ib": ("mode", ["break", "fade"]),
         "gap": ("mode", ["fill", "go"]), "lon_break": ("min_rng_atr", [0.0, 1.0, 2.0]), "first_bar_mom": ("k", [1.0, 1.5, 2.0]),
         "mid_fade": ("k", [0.15, 0.3, 0.6])}
STOPV, TGTR = [1.0, 2.0, 3.0], [0.5, 1.0, 2.0, 3.0]
FP_STOP_PTS, FP_TGT = [3.0, 6.0, 10.0, 15.0], [0.25, 0.4, 0.6, 1.0]     # ES points (NQ used {10,20,30,45}); ES ~ 1/3.5 of NQ's point size


def grid(key, stage, strat, inputs, axes):
    n = 1
    for a in axes:
        n *= len(a["values"])
    return {"key": key, "kind": "grid", "stage": stage, "pilot": "es", "strategy": strat, "inputs": inputs, "axes": axes, "max_cells": n,
            "range": RNG, "costs": {"qty": 1}, "prop_rules": PR}


def hm(fam, tf):
    if fam == "tod_drift":
        ax = [{"key": "off_min", "values": [0, 15, 30, 60]}, {"key": "exit_bars", "values": [6, 12, 24]}, {"key": "dir", "values": ["long", "short"]}]
    else:
        k, v = FAMAX[fam]
        ax = [{"key": k, "values": v}, {"key": "stop_val", "values": STOPV}, {"key": "tgt_r", "values": TGTR}]
    return grid(f"hm-{fam}-tf{tf}", "sizing", S(fam), {"tf": str(tf), "sess": "all"}, ax)


def fp(fam, tf):
    inp = {"tf": str(tf), "sess": "all", "stop_mode": "pts"}
    if fam == "tod_drift":
        inp["exit_bars"] = 0
    return grid(f"fp-{fam}-tf{tf}", "sizing", S(fam), inp,
                [{"key": "stop_val", "values": FP_STOP_PTS}, {"key": "tgt_r", "values": FP_TGT}])


def tune(picks_file):
    pk = json.load(open(picks_file))
    out = [hm(f, t) for f, t in pk["hm"]] + [fp(f, t) for f, t in pk["fp"]]
    hm_tfs = sorted({int(t) for f, t in pk["hm"] if f != "tod_drift"}, key=int)
    fp_tfs = sorted({int(t) for f, t in pk["fp"]}, key=int)
    for t in hm_tfs:
        for s in (11, 12, 13):
            out.append(grid(f"hmctrl-random-tf{t}-s{s}", "ctrl", S("random"), {"tf": str(t), "sess": "all", "p_entry": 0.5, "seed": s},
                            [{"key": "stop_val", "values": STOPV}, {"key": "tgt_r", "values": TGTR}]))
    for t in sorted({int(t) for f, t in pk["hm"] if f == "tod_drift"}):      # time-exit profile (tod_drift heat-map axis exit_bars)
        for s in (11, 12, 13):
            out.append(grid(f"hmctrl-randomtod-tf{t}-s{s}", "ctrl", S("random"), {"tf": str(t), "sess": "all", "p_entry": 0.5, "seed": s, "tgt_r": 0.0, "max_tr": 1},
                            [{"key": "exit_bars", "values": [6, 12, 24]}]))
    for t in fp_tfs:
        for s in (21, 22, 23):
            out.append(grid(f"fpctrl-random-tf{t}-s{s}", "ctrl", S("random"), {"tf": str(t), "sess": "all", "stop_mode": "pts", "p_entry": 0.5, "seed": s},
                            [{"key": "stop_val", "values": FP_STOP_PTS}, {"key": "tgt_r", "values": FP_TGT}]))
    return out


if __name__ == "__main__":
    if sys.argv[1] == "tune":
        for j in tune(sys.argv[2]):
            print(json.dumps(j))
    else:
        for j in sum((globals()[a]() for a in sys.argv[1:]), []):
            print(json.dumps(j))
