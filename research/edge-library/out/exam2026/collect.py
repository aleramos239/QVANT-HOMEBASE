"""Every number of the out-of-sample report, from the stores through judge.py (read-only): out/exam2026/oos.json.
2026 rows exist only for the units on allowed.json (judge.RULE['exam'] = True is refused for every other unit)."""
import json
import sys
from pathlib import Path

W = Path(__file__).resolve().parents[2]
sys.dont_write_bytecode = True
sys.path.insert(0, str(W))
import judge as J  # noqa: E402

UNITS = ["straddle_tight_0830-NQ-tf30-pre", "straddle_tight_0830-NQ-tf30-pre@A", "straddle_tight_0830-NQ-tf30-pre@B",
         "straddle_tight_0830-GC-tf30-pre@A", "straddle_tight_0830-GC-tf30-pre@B", "straddle_tight_1000-NQ-tf30-nyam@C",
         "straddle_tight_1000-GC-tf30-nyam@C", "first_bar_mom-NQ-tf30-mid", "first_bar_mom-NQ-tf15-mid", "first_bar_mom-ES-tf15-mid",
         "orb-NQ-tf15-pre", "tema_slope-NQ-tf30-eve", "donchian-NQ-tf30-nyam", "straddle_t_0830-NQ-tf30-pre", "straddle_t_1800-NQ-tf30-eve"]


def ctl(det):
    out = {}
    for c, v in det.items():
        out[c] = {k: v.get(k) for k in ("pass", "lift", "p_beat", "lift_per_trade", "per_trade", "unfiltered_per_trade", "seeds", "two_seed") if k in v}
        if "seeds" in out[c]:
            out[c]["seeds"] = len(out[c]["seeds"])
    return out


def one(addr):
    u = J.unit(addr)
    m = J.member(u)
    j = m["judge"]
    r = {"unit": addr, "name": m["name"], "default": m["default"], "variants": m["variants_judged"], "saved": len(m["surviving"]),
         "demoted_2024": bool(j["pick"]["demoted"]), "pick_verdict": j["pick"]["verdict"],
         "build": {"share_pos": j["build"]["share_pos"], "avg_net": j["build"]["avg_net"], "controls": ctl(j["build"]["controls"])},
         "avg_rows": {x["period"]: x for x in m["avg_rows"]}, "default_rows": {str(x["period"]).rstrip("*"): x for x in m["default_rows"]},
         "exam_refused": j.get("exam_refused")}
    for p in ("pick", "check", "exam"):
        if p not in j:
            continue
        y = j[p]
        r[p] = {k: y.get(k) for k in ("verdict", "t4", "t5", "t6", "cells", "positive", "share_pos", "avg_net", "median_net", "avg_trades",
                                      "stress_avg_net", "stress_share_pos", "default_net", "default_stress_net", "saved_profitable", "failed")}
        r[p]["controls"] = ctl(y["controls"])
        r[p]["fast_net_share"] = m["fast_avg"][p]["fast_net_share"]
        r[p]["fast_profit_share"] = m["fast_avg"][p]["fast_profit_share"]
    r["fast_net_share_all"] = m["fast_avg"]["all"]["fast_net_share"]
    return r


if __name__ == "__main__":
    J.RULE["exam"] = True                                  # opens 2026 for the allowed units only (exam_gate)
    out = [one(a) for a in (sys.argv[1:] or UNITS)]
    (W / "out" / "exam2026" / "oos.json").write_text(json.dumps(out, indent=1, default=float))
    for r in out:
        a, d = r["avg_rows"], r["default_rows"]
        print(r["unit"], "| 2025", r["check"]["verdict"], "| 2026", (r.get("exam") or {}).get("verdict", "not run"),
              "| avg", " ".join(f"{k}:{a[k]['net']:.0f}" for k in a if k != "combined"),
              "| default", " ".join(f"{k}:{d[k]['net']:.0f}" for k in d if k != "combined"))
