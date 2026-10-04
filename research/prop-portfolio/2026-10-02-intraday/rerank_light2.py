#!/usr/bin/python3
"""rerank.py light stages, part 2: SECOND LOOK on R's existing 2025+ bundles, the four desk algos, summary.md.

SECOND LOOK = the 2025-01 -> 2026-09 holdout was spent once on R's frozen finalists. Nothing here selects on it: the picks and their
rules come from the in-sample intraday search; a pick is re-scored on 2025+ only when R happens to hold a holdout bundle for its config.
"""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import datetime as dt                   # noqa: E402
import json                             # noqa: E402
import zlib                             # noqa: E402
from pathlib import Path                # noqa: E402
from types import SimpleNamespace       # noqa: E402

import numpy as np                      # noqa: E402

HO_START, HO_END = "2025-01-01", "2026-09-30"


def _bind(mod, rl):
    global RR, RL, S, E, F, P, A2, A3, FS, WF, ROUT, OUT, HERE
    RR, RL = mod, rl
    S, E, F, P, A2, A3, FS, WF, ROUT, OUT, HERE = mod.S, mod.E, mod.F, mod.P, mod.A2, mod.A3, mod.FS, mod.WF, mod.ROUT, mod.OUT, mod.HERE


# ------------------------------------------------------------------ R's frozen holdout path with explicit rules

_CTX = {}


def ctx_of(mode):
    """holdout_score's context: 'insample' (2021-24 sources) or 'holdout' (R's finished 2025+ runs of the 41 manifest configs)."""
    if mode not in _CTX:
        import holdout_score as HS
        man = RL.manifest()
        _CTX[mode] = (HS, man, HS.make_ctx(man, mode))
    return _CTX[mode]


def eval_at(mode, firm, key, sess, micros, rules, boots=1000, lift=True):
    HS, man, ctx = ctx_of(mode)
    fm = P.firm(firm)
    members = [(ctx.base(HS.cand_of(man, key, sess)), int(micros))]
    res, A, _ = HS.eval_cell(ctx, fm, P.PV(members, ctx.D), rules)
    out = {m: P._detail(res[m][0], res[m][1], boots if m == "intraday" else 0) for m in E.MODELS}
    out["n_starts"], out["trades"] = int(ctx.S), int(members[0][0].n)
    if lift:
        cp = []
        for c in ctx.controls(members[0][0]):
            r, _, _ = HS.eval_cell(ctx, fm, P.PV([(c, int(micros))], ctx.D), rules)
            cp.append(r["intraday"][0] == 1)
        c = np.mean(np.stack(cp), 0)
        real = (res["intraday"][0] == 1).astype(float)
        out["lift_intraday"] = dict(K=len(cp), ctrl_p5=float(c.mean()), lift=float((real - c).mean()), ci=E.block_ci([real - c], boots=boots)[0])
    return out


def funded_at(mode, variant, key, sess, micros, rules, policy, lift=True):
    HS, man, ctx = ctx_of(mode)
    f, dll = HS.VARIANTS[variant]
    Sp = F.make_spec(f, dll)
    t = ctx.res.tr(key)
    idx = np.flatnonzero(E._sess_mask(t, sess))
    port = HS.Port2(t.date[idx], t.te[idx], t.tx[idx], t.side[idx], t.g[idx], t.mae[idx], t.mfe[idx], t.risk[idx], ctx.cal)
    rl = {k: rules[k] for k in ("day_take", "day_lock", "day_stop", "max_day_tr")}
    src = F.DaySrc(port, rl, int(micros), events=False)
    out = {m: F.metrics(F.lifecycle(Sp, src, policy, HS.HL, m), HS.HL) for m in ("intraday", "realized")}
    out["n_starts"], out["trades"] = HS.port_starts(port), int(len(idx))
    if lift:
        cand = HS.cand_of(man, key, sess, "ctrl_funded")
        pool, _ = ctx.pool_tr(cand)
        sub = SimpleNamespace(date=t.date[idx], sess=t.sess[idx], n=len(idx))
        cs = E.daymatched_controls(sub, pool, K=ctx.K, seed=zlib.crc32(f"fund|{cand['cid']}".encode()), mask=None,
                                   carry=("side", "g", "mae", "mfe", "risk", "sess"))
        ce = []
        for c in cs:
            cp = HS.Port2(c["date"], c["te"], c["tx"], c["side"], c["g"], c["mae"], c["mfe"], c["risk"], ctx.cal)
            ce.append(F.metrics(F.lifecycle(Sp, F.DaySrc(cp, rl, int(micros), events=False), policy, HS.HL, "intraday"), HS.HL)["e_net_40"])
        out["lift_intraday"] = dict(K=len(ce), ctrl_e40=float(np.mean(ce)), lift_e40=float(out["intraday"]["e_net_40"] - np.mean(ce)))
    return out


def _policy(x):
    return x if x == "max" else int(float(x))


def stage_second():
    et = json.loads((OUT / "eval_top.json").read_text())
    ft = json.loads((OUT / "funded_top.json").read_text()) if (OUT / "funded_top.json").exists() else {"top": {}}
    man = RL.manifest()
    have = set(man["configs"])
    res = {"label": "SECOND LOOK (the 2025+ holdout was already spent on R's finalists; never a clean exam, never selected on)",
           "control": "unbiased day-matched draw (overlap allowed)" if RR.CTRL_UNBIASED else "R's day-matched draw (no overlap: biased for multi-trade configs)",
           "window": [HO_START, HO_END], "eval": [], "funded": [], "no_bundle": {"eval": [], "funded": []}, "insample_path_check": []}
    for f in RR.LUCID + ("apex", "apex_eod"):
        for r in et["top"][f]:
            tag = f"{f}: {r['key']} {r['sess']}"
            key = r["key"]
            if key not in have:      # no bundle of its own: a twin (identical entries and identical in-sample result at this cell) may have one
                tw = [x for x in (r.get("same_trade") or "").split(";") if x in have]
                if not tw:
                    res["no_bundle"]["eval"].append(tag)
                    continue
                key = tw[0]
            rules = {k: r[k] for k in ("day_lock", "day_take", "day_stop", "max_day_tr", "target_take")}
            ins = eval_at("insample", f, key, r["sess"], r["micros"], rules, boots=0, lift=False)
            res["insample_path_check"].append(dict(pick=tag, stored=r["intraday_p5"], recomputed=ins["intraday"]["p5"],
                                                   diff=abs(ins["intraday"]["p5"] - r["intraday_p5"])))
            ho = eval_at("holdout", f, key, r["sess"], r["micros"], rules)
            res["eval"].append(dict(firm=f, rank=r["rank"], key=r["key"], via_twin=key if key != r["key"] else None, sess=r["sess"], micros=r["micros"], rules=rules, is_intraday_p5=r["intraday_p5"],
                                    is_realized_p5=r["realized_p5"], is_lift=r["lift_intraday_p5"], ho_trades=ho["trades"], ho_n_starts=ho["n_starts"],
                                    ho_intraday={k: ho["intraday"][k] for k in ("p1", "p2", "p3", "p5", "bust5", "med_days")},
                                    ho_intraday_ci=ho["intraday"].get("ci_p5"), ho_realized_p5=ho["realized"]["p5"], ho_eod_p5=ho["eod"]["p5"],
                                    ho_lift_intraday=ho["lift_intraday"]))
            print(f"second eval {tag}: IS {r['intraday_p5']:.3f} -> HO {ho['intraday']['p5']:.3f} (lift {ho['lift_intraday']['lift']:+.3f})", flush=True)
    for v in RR.LV:
        for r in ft["top"].get(v, []):
            tag = f"{v}: {r['key']} {r['sess']}"
            if r["key"] not in have:
                res["no_bundle"]["funded"].append(tag)
                continue
            rules = {k: r[k] for k in ("day_take", "day_lock", "day_stop", "max_day_tr")}
            ins = funded_at("insample", v, r["key"], r["sess"], r["micros"], rules, _policy(r["policy"]), lift=False)
            res["insample_path_check"].append(dict(pick=tag, stored=r["e_net_40"], recomputed=ins["intraday"]["e_net_40"],
                                                   diff=abs(ins["intraday"]["e_net_40"] - r["e_net_40"])))
            ho = funded_at("holdout", v, r["key"], r["sess"], r["micros"], rules, _policy(r["policy"]))
            res["funded"].append(dict(variant=v, rank=r["rank"], key=r["key"], sess=r["sess"], cell=r["cell"], is_e40=r["e_net_40"], is_wf_oos_e40=r.get("wf_oos_e_net_40"),
                                      ho_trades=ho["trades"], ho_n_starts=ho["n_starts"],
                                      ho_intraday={k: ho["intraday"][k] for k in ("e_net_40", "p_pay_20", "p_pay_40", "med_days_first", "p_bust_pre_first")},
                                      ho_realized_e40=ho["realized"]["e_net_40"], ho_lift_intraday=ho["lift_intraday"]))
            print(f"second funded {tag}: IS E$40 {r['e_net_40']:.0f} -> HO {ho['intraday']['e_net_40']:.0f}", flush=True)
    res["max_path_diff"] = max((x["diff"] for x in res["insample_path_check"]), default=None)
    RL.jdump(OUT / "second_look.json", res)
    print("second look: eval", len(res["eval"]), "funded", len(res["funded"]), "no bundle", {k: len(v) for k, v in res["no_bundle"].items()},
          "max in-sample path diff", res["max_path_diff"], flush=True)


# ------------------------------------------------------------------ the four desk algos

DESK = {
    "nq_nyam_flex": dict(kind="eval", what="Flex eval", firm="lucid", fid="lucid:single", key="hm2-straddle-tf30#10", sess="nyam", micros=40,
                         rules={"day_lock": 750, "day_take": 1500, "day_stop": 0, "max_day_tr": 0, "target_take": 1}, runs={40: "nq_nyam_flex_4nq"}),
    "nq_nyam_pro": dict(kind="eval", what="Pro noDLL eval", firm="lucidpro_nodll", fid="lucidpro_nodll:single", key="hm2-straddle-tf30#10", sess="nyam", micros=40,
                        rules={"day_lock": 1000, "day_take": 0, "day_stop": 0, "max_day_tr": 0, "target_take": 1}, runs={40: "nq_nyam_pro_4nq"}),
    "nq_orb_pro": dict(kind="funded", what="Pro noDLL funded", variant="pro_nodll", fid="pro_nodll#1", key="hm-orb-tf5#10", sess="mid", micros=40, policy=1000,
                       rules={"day_take": 1000, "day_lock": 300, "day_stop": 0, "max_day_tr": 0}, runs={40: "nq_orb_pro_4nq"}),
    "nq_pm_flex": dict(kind="funded", what="Flex funded", variant="flex", fid="flex#1", key="hm2-straddle-tf30#32", sess="pm", micros=40, policy=1500,
                       rules={"day_take": 600, "day_lock": 300, "day_stop": 0, "max_day_tr": 0}, runs={20: "nq_pm_flex_2nq", 30: "nq_pm_flex_3nq", 40: "nq_pm_flex_4nq"}),
}
MLL = 2000.0


def desk_rows(name):
    """Tick-replayed desk-version run (take = a real limit exit: mae_usd is the open loss BEFORE the exit). -> (in-sample rows, 2025+ rows)."""
    t = json.loads((HERE / "desk_runs" / name / "trades.json").read_text())
    return [x for x in t if x["date"] < HO_START], [x for x in t if x["date"] >= HO_START]


class TierSrc:
    """DaySrc stand-in for funded.simulate: one desk-version run per size tier (the $ take is fixed, so its points differ per tier).
    get(i, cap, ...) -> (day P&L, worst open point, lowest realised, executed, ...) of the tier's run on calendar day i."""

    def __init__(self, rows_by_cap: dict, cal_iso: list):
        pos = {d: i for i, d in enumerate(cal_iso)}
        self.n_days = len(cal_iso)
        self.day = {}
        for cap, rows in rows_by_cap.items():
            dd = {}
            for x in rows:
                if x["date"] in pos:
                    assert pos[x["date"]] not in dd, "one trade a day expected"
                    net = float(x["net"])
                    dd[pos[x["date"]]] = (net, min(net, -abs(float(x["mae_usd"])) - float(x["commission"])), min(net, 0.0), 1, (), (), 0, ())
            self.day[cap] = dd

    def get(self, i, cap, dll=0.0, lim=0.0):
        return self.day[cap].get(i, (0.0, 0.0, 0.0, 0, (), (), 0, ()))


def _open_loss(rows):
    mae = np.array([abs(float(x["mae_usd"])) + float(x["commission"]) for x in rows])
    tp = np.array([x["exit_reason"] == "tp" for x in rows])
    net = np.array([float(x["net"]) for x in rows])
    stop = np.array([abs(float(x["entry_price"]) - float(x["sl"])) * E.PL.PV * float(x["qty"]) for x in rows if x.get("sl")])     # $ from entry to the stop
    return dict(days=len(rows), take_days=float(tp.mean()), open_loss_ge_mll=float((mae >= MLL).mean()),
                stop_usd_median=float(np.median(stop)), stop_usd_p10=float(np.percentile(stop, 10)), stop_usd_p90=float(np.percentile(stop, 90)),
                open_loss_ge_mll_on_take_days=float((mae >= MLL)[tp].mean()) if tp.any() else None,
                take_before_mll=float((tp & (mae < MLL)).mean()), mean_day_net=float(net.mean()),
                median_open_loss=float(np.median(mae)))


def _full_trade_share(mode, key, sess, micros):
    """Research trades (the exit is the 3-ATR stop / 2R target / flat time, the take is only a rule): share of trades whose FULL-trade MAE at
    desk size reaches the max loss. This is what R's 'intraday' model charges, even on days the take would have closed the trade first."""
    HS, man, ctx = ctx_of(mode)
    t = ctx.res.tr(key)
    m = E._sess_mask(t, sess)
    return float(((t.mae[m] * micros / 10.0 + E.cost(micros)) >= MLL).mean())


def stage_desk():
    hres = json.loads((ROUT / "holdout_results.json").read_text())
    vres = json.loads((ROUT / "holdout_validate_insample.json").read_text())
    cal = {"is": S.in_sample_sessions(), "ho": S.tape_sessions(HO_START, HO_END, allow_holdout=True)}
    out = {}
    for name, a in DESK.items():
        o = {"what": a["what"], "config": f"{a['key']} {a['sess']}", "micros": a["micros"], "rules": a["rules"], "policy": a.get("policy")}
        for w, src, mode in (("is", vres, "insample"), ("ho", hres, "holdout")):
            x = src["eval" if a["kind"] == "eval" else "funded"][a["fid"]]
            if a["kind"] == "eval":
                o[f"R_{w}"] = {m: {k: x[m][k] for k in ("p1", "p3", "p5", "bust5")} for m in ("realized", "intraday")}
            else:
                o[f"R_{w}"] = {m: {k: x[m][k] for k in ("e_net_40", "p_pay_20", "p_pay_40", "med_days_first", "p_bust_pre_first")} for m in ("realized", "intraday")}
            o[f"full_trade_open_loss_share_{w}"] = _full_trade_share(mode, a["key"], a["sess"], a["micros"])
        rows = {cap: desk_rows(nm) for cap, nm in a["runs"].items()}
        for wi, w in enumerate(("is", "ho")):
            kw = {} if w == "is" else dict(calendar=cal["ho"], allow_holdout=True)
            top = rows[max(rows)][wi]
            o[f"desk_open_loss_{w}"] = {f"{cap // 10}nq": _open_loss(r[wi]) for cap, r in sorted(rows.items())}
            if a["kind"] == "eval":
                rl = dict(a["rules"], day_take=0)                       # the take is the run's own limit exit
                r = S.score_eval(top, a["firm"], rl, micros=a["micros"], sess="all", boots=1000, **kw)
                o[f"desk_{w}"] = {m: {k: r["models"][m][k] for k in ("p1", "p2", "p3", "p5", "bust5", "med_days")} for m in ("realized", "intraday")}
                o[f"desk_{w}"]["intraday_ci_p5"] = S.score_eval(top, a["firm"], rl, "intraday", micros=a["micros"], sess="all", boots=1000, **kw).get("ci_p5")
            else:
                f, dll = FS.VARIANTS[a["variant"]]
                Sp = F.make_spec(f, dll)
                src = TierSrc({cap: r[wi] for cap, r in rows.items()} if len(rows) > 1 else {Sp.cap: top}, cal[w])
                o[f"desk_{w}"] = {}
                for m in ("realized", "intraday"):
                    mm = F.metrics([F.simulate(Sp, src, s, F.H_LIFE, a["policy"], m) for s in range(src.n_days - F.H_LIFE + 1)], F.H_LIFE)
                    o[f"desk_{w}"][m] = {k: mm[k] for k in ("e_net_40", "p_pay_20", "p_pay_40", "med_days_first", "p_bust_pre_first")}
        out[name] = o
        d, R_ = o["desk_is"], o["R_is"]
        k = "p5" if a["kind"] == "eval" else "e_net_40"
        print(f"{name}: in-sample {k} realized R {R_['realized'][k]:.3f} | R intraday (worst-first bound) {R_['intraday'][k]:.3f} | "
              f"desk run true-order intraday {d['intraday'][k]:.3f} (realized {d['realized'][k]:.3f}); HO {o['desk_ho']['intraday'][k]:.3f}; "
              f"open loss >= $2,000 before exit: {o['desk_open_loss_is'][max(o['desk_open_loss_is'])]['open_loss_ge_mll']:.2f} of days "
              f"(full-trade {o['full_trade_open_loss_share_is']:.2f})", flush=True)
    RL.jdump(OUT / "desk_algos.json", out)


def stage_ctrl_bias(K=5):
    """Evidence for the control switch (rerank.py): for every reported pick that trades more than once a day, the mean $ per trade (1 NQ) of
    its random pool in that session, of R's day-matched control (no overlap) and of the unbiased draw (overlap allowed) -> out/control_bias.json."""
    et = json.loads((OUT / "eval_top.json").read_text())
    ft = json.loads((OUT / "funded_top.json").read_text())
    picks = {(r["key"], r["sess"]): int(r["pass"] == 2) for f in RR.LUCID for r in et["top"][f] if (r.get("max_tr_day") or 0) > 1}
    picks.update({(r["key"], r["sess"]): int(not r["key"].startswith(("hm2-", "fp-"))) for v in RR.LV for r in ft["top"][v] if (r.get("max_tr_day") or 0) > 1})
    srcs = {s[3]: s for s in A3.sources3()}
    srcs.update({s[3]: s for s in A3.sources2()})
    draw = getattr(RR, "_R_DMC", E.daymatched_controls)             # R's own function, whatever the switch
    rows = []
    for (key, sess), p2 in sorted(picks.items()):
        src, fam, tf, _, params = srcs[key]
        t = A2.load_src(src)
        prof = E.profile_from(fam, dict(params, tf=tf))
        pool = A2.pool_of(A3.resolve(prof, bool(p2))["srcs"])
        idx = np.flatnonzero(t.sess == E.SESS_CODE[sess])
        sub = SimpleNamespace(date=t.date[idx], sess=t.sess[idx], n=len(idx))
        pm = pool.sess == E.SESS_CODE[sess]
        o = dict(key=key, sess=sess, stop=f"{prof['stop_mode']} {prof['stop_val']}", tgt_r=prof["tgt_r"], trades_per_day=float(len(idx) / len(set(t.date[idx].tolist()))),
                 pool_mean=float(pool.g[pm].mean()), pool_win=float((pool.g[pm] > 0).mean()))
        for nm, no in (("r", True), ("u", False)):
            cs = draw(sub, pool, K=K, seed=zlib.crc32(f"{key}|{sess}".encode()), mask=None, no_overlap=no, carry=("g",))
            first = [c["g"][np.r_[True, c["date"][1:] != c["date"][:-1]]].mean() for c in cs]
            o[f"ctrl_{nm}_mean"], o[f"ctrl_{nm}_first_trade_mean"] = float(np.mean([c["g"].mean() for c in cs])), float(np.mean(first))
            o[f"ctrl_{nm}_minutes"] = float(np.mean([((c["tx"] - c["te"]) / 60000).mean() for c in cs]))
        o["bias_r"], o["bias_u"] = o["ctrl_r_mean"] - o["pool_mean"], o["ctrl_u_mean"] - o["pool_mean"]
        rows.append(o)
        print(f"ctrl_bias {key} {sess}: pool ${o['pool_mean']:.1f} a trade; R's control ${o['ctrl_r_mean']:.1f} (first trade of the day ${o['ctrl_r_first_trade_mean']:.1f}); "
              f"unbiased draw ${o['ctrl_u_mean']:.1f} (first ${o['ctrl_u_first_trade_mean']:.1f})", flush=True)
    RL.jdump(OUT / "control_bias.json", {"what": "mean gross $ per trade at 1 NQ; R's day-matched control keeps non-overlapping random trades only", "K": K, "rows": rows})


def stage_summary():
    import rerank_summary as RS
    RS.write(RR, RL, sys.modules[__name__])
