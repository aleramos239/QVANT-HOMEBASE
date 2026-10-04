#!/usr/bin/python3
"""Build (and with --freeze, FREEZE) the holdout manifest of a pilot: out/holdout_manifest.json + out/holdout_manifest.sha256.

Reads ONLY in-sample artefacts (out/portfolio_results.json, portfolio_members.md [via the json], funded_summary.md, funded_candidates.csv,
candidates.csv, a3p3 / a3p2 snapshots, ledger.csv, jobs.jsonl) and the tick-archive MANIFESTS (file names / session dates, never ticks or results).
Finalists are chosen by the rules written in this file from in-sample numbers only; nothing is looked up from 2025+.

  build_holdout_manifest.py            dry run: prints the summary, writes out/holdout_manifest.draft.json
  build_holdout_manifest.py --freeze   writes out/holdout_manifest.json and its sha256 (the hb.py 'holdout' stage only accepts those jobs)
  build_holdout_manifest.py --jobs F   (after the freeze) writes the job lines of the manifest to F for `hb.py submit F`

NQ only for now (PP_PILOT / --pilot selects the pilot dir; the ES manifest uses the same code with its own out/ files).
"""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import json
import re
import sys
from collections import OrderedDict
from pathlib import Path

CODE = Path(__file__).resolve().parent
sys.path.insert(0, str(CODE))
import evalcore as E          # noqa: E402
import funded as F            # noqa: E402
import holdout_score as HS    # noqa: E402

D, OUT = E.D, E.D / "out"
FIRMS = ("lucid", "lucidpro", "lucidpro_nodll", "apex", "apex_eod")
APEX = ("apex", "apex_eod")
L2, J2 = HS.P.SNAP_L, HS.P.SNAP_J                    # pass-2 snapshot (NQ a3p2; ES a3p3s)
L3, J3 = OUT / "a3p3_snap_ledger.csv", OUT / "a3p3_snap_jobs.jsonl"
HO_START = "2025-01-01"
VARIANT_NAMES = {"Flex": "flex", "Flex+DLL1200*": "flex_dll", "Pro DLL": "pro_dll", "Pro noDLL": "pro_nodll", "Apex PA (UNCONF.)": "apex"}
# the three research-window ledgers / the live ledger: key -> ledger row
LEDGER = list(csv.DictReader((D / "ledger.csv").open(newline="")))


def canon(o) -> str:
    return json.dumps(o, sort_keys=True, separators=(",", ":"))


def data_end() -> tuple:
    """Latest COMPLETE archive session of the root (manifest file names + 'complete' flag only) and the holdout calendar facts."""
    best, partial = {}, []
    root = Path.home() / "futures_ticks" / E.ROOT
    for m in sorted(root.glob("20[2-9][0-9]/*.json")):
        if ".live" in m.name:
            continue
        try:
            j = json.loads(m.read_text())
        except (OSError, ValueError):
            continue
        d = m.name[:10]
        if d < HO_START or dt.date.fromisoformat(d).weekday() >= 5:
            continue
        n = int(j.get("ticks", 0))
        if d not in best or n > best[d][1]:
            best[d] = (j.get("contract"), n, bool(j.get("complete")))
    done = sorted(d for d, v in best.items() if v[2])
    partial = sorted(d for d, v in best.items() if not v[2])
    return done[-1], len(best), partial


# ------------------------------------------------------------------ ledger lookups

def ledger_row(key: str) -> dict:
    """'hm2-straddle-tf30#10' -> the sizing-stage grid cell row; 'screen-orb-tf5' -> the screen run row."""
    if "#" in key:
        k, c = key.rsplit("#", 1)
        rows = [r for r in LEDGER if r["stage"] == "sizing" and r["key"] == k and r["cell"] == c and r["grid_id"]]
    else:
        rows = [r for r in LEDGER if r["stage"] == "screen" and r["key"] == key and r["run_id"]]
    if len(rows) != 1:
        raise KeyError(f"{key}: {len(rows)} ledger rows")
    return rows[0]


def src_of(r: dict) -> str:
    return r["run_id"] if r["run_id"] else f"{r['grid_id']}#{r['cell']}"


_CTRL = None


def ctrl_rows() -> dict:
    global _CTRL
    if _CTRL is None:
        _CTRL = {src_of(r): r for r in LEDGER if r["stage"] == "ctrl" and r["strategy"] == E.DRAFT_PREFIX + "random" and (r["run_id"] or r["grid_id"])}
    return _CTRL


# ------------------------------------------------------------------ manifest parts

class Builder:
    def __init__(self, end: str):
        self.end = end
        self.rng = {"preset": "custom", "start": HO_START, "end": end}
        self.configs: OrderedDict = OrderedDict()      # key -> entry
        self.controls: OrderedDict = OrderedDict()     # control id -> entry
        self.cand_pass: dict = {}
        self.cand_rows: dict = {}
        for r in csv.DictReader((OUT / "candidates.csv").open()):
            self.cand_pass.setdefault(r["key"], r["pass"])
            self.cand_rows.setdefault((r["firm"], r["key"], r["sess"]), r)

    # control pool of a config: ledger-snapshot resolution exactly as the in-sample code did it
    def pool(self, fam: str, tf: int, params: dict, old: bool) -> dict:
        led, jobs = (L2, J2) if old else (L3, J3)
        pl = E.resolve_pool(E.profile_from(fam, dict(params, tf=tf)), led, jobs)
        if not pl["srcs"]:
            raise RuntimeError(f"no control pool for {fam} tf{tf}")
        ids = []
        for s in pl["srcs"]:
            r = ctrl_rows()[s]
            cid = r["key"] + (f"#{r['cell']}" if r["cell"] != "" else "")
            ids.append(cid)
            if cid not in self.controls:
                self.controls[cid] = {"strategy": r["strategy"], "inputs": json.loads(r["params_json"]), "in_sample_src": s, "ledger_key": r["key"],
                                      "cell": r["cell"], "job_key": "hoc-" + cid.replace("#", "-c")}
        return {"ids": ids, "flag": pl["flag"] or "exact", "profile": pl["profile"], "exact": pl["exact"]}

    def meta(self, key: str) -> dict:
        """Config facts of a ledger key WITHOUT registering it as a finalist config (no control pool, no job)."""
        r = ledger_row(key)
        inputs = json.loads(r["params_json"])
        return {"row": r, "inputs": inputs, "params": {k: v for k, v in inputs.items() if k not in ("tf", "sess")} if "#" in key else {},
                "tf": int(inputs["tf"]), "fam": r["strategy"].replace(E.DRAFT_PREFIX, "")}

    def cfg(self, key: str, pass_: str | None = None) -> str:
        if key in self.configs:
            return key
        mt = self.meta(key)
        r, inputs, params, tf, fam = mt["row"], mt["inputs"], mt["params"], mt["tf"], mt["fam"]
        pass_ = pass_ or self.cand_pass.get(key, "3")
        h = hashlib.sha1((r["strategy"] + canon(inputs)).encode()).hexdigest()[:8]
        self.configs[key] = {"strategy": r["strategy"], "inputs": inputs, "fam": fam, "tf": tf, "params": params, "ledger_key": r["key"], "cell": r["cell"],
                             "in_sample_src": src_of(r), "candidate_pass": pass_, "job_key": f"ho-{fam}-tf{tf}-{h}",
                             "ctrl_eval": self.pool(fam, tf, params, pass_ == "2"), "ctrl_funded": self.pool(fam, tf, params, False)}
        return key

    def jobs(self) -> list:
        out, seen = [], {}
        for kind, d in (("finalist", self.configs), ("control", self.controls)):
            for k, c in d.items():
                if c["job_key"] in seen:                    # same strategy + inputs reached by two keys: ONE run
                    c["job_key"] = seen[c["job_key"]]
                    continue
                seen[c["job_key"]] = c["job_key"]
                out.append({"key": c["job_key"], "kind": "run", "stage": "holdout", "strategy": c["strategy"], "inputs": c["inputs"], "range": self.rng,
                            "costs": {"qty": 1}, "role": kind, "source_key": k})
        return out


def parse_rules(s: str) -> tuple:
    """'m40 L750 K1500 S- T- TT' -> (micros, rules dict)."""
    g = re.match(r"m(\d+) L(\S+) K(\S+) S(\S+) T(\S+) (\w+)", s).groups()
    n = lambda x: 0 if x == "-" else int(x)
    return int(g[0]), {"day_lock": n(g[1]), "day_take": n(g[2]), "day_stop": n(g[3]), "max_day_tr": n(g[4]), "target_take": int(g[5] == "TT")}


def fnum(x, d=None):
    try:
        return float(x)
    except (TypeError, ValueError):
        return d


def apex_flag_list(b: Builder, members: list, rules: dict) -> list:
    out = []
    for m in members:
        c = b.configs.get(m["cfg"]) or b.meta(m["cfg"])
        prof = E.profile_from(c["fam"], dict(c["params"], tf=c["tf"]))
        fi = json.loads(E.PL.shared("family_inputs.json").read_text())
        dflt = {row[0]: row[2] for row in fi.get(c["fam"], []) if len(row) > 3}
        inputs = {**{a: v for a, v in dflt.items() if a in ("sq_type", "mode")}, **c["params"], "tgt_r": prof["tgt_r"]}
        for f in F.apex_flags(c["fam"], inputs, {"day_stop": rules.get("day_stop", 0)}, None):
            if f not in out:
                out.append(f)
    return out


def finalists(b: Builder) -> tuple:
    res = json.loads((OUT / "portfolio_results.json").read_text())
    fins: OrderedDict = OrderedDict()
    sigs: dict = {}

    def add(fid: str, firm: str, role: str, members: list, rules: dict, insample: dict, note: str = ""):
        sig = (firm, tuple((m["cfg"], m["sess"], m["micros"]) for m in members), canon(rules))
        if sig in sigs:                                     # identical to an existing finalist: one score, extra role
            fins[sigs[sig]]["roles"].append(role)
            fins[sigs[sig]]["aliases"].append(fid)
            return sigs[sig]
        sigs[sig] = fid
        flags = apex_flag_list(b, members, rules) if firm in APEX else []
        fins[fid] = {"firm": firm, "role": role, "roles": [role], "aliases": [], "members": members, "rules": rules, "apex_flags": flags,
                     "insample": insample, "note": note}
        return fid

    def from_report(firm: str, lab: str, rep: dict, role: str, fid: str, fast: bool = False):
        mem = []
        for m in rep["members"]:
            key, sess = m["name"].split("|")
            mem.append({"cfg": b.cfg(key), "sess": sess, "micros": int(m["micros"])})
        c = rep["cell"]
        rules = {k: int(c[k]) for k in ("day_lock", "day_take", "day_stop", "max_day_tr", "target_take")}
        ins = {}
        if "headline" in rep:
            h = rep["headline"]
            ins = {"p1": h["p1"], "p2": h["p2"], "p3": h["p3"], "p5": h["p5"], "bust5": h["bust5"], "ci_p5": h.get("ci_p5"), "model": h["model"],
                   "eod_p5": rep["eod"]["p5"], "realized_p5": rep["realized"]["p5"], "intraday_p5": rep["intraday"]["p5"]}
            if rep.get("lift"):
                L = rep["lift"][h["model"]]
                ins["lift"], ins["lift_ci"] = L["lift"], L["ci"]
            if rep.get("wf_fixed"):
                ins["wf_oos_p5"], ins["wf_oos_lift"], ins["wf_oos_ci"] = rep["wf_fixed"]["oos_p5"], rep["wf_fixed"].get("lift"), rep["wf_fixed"].get("ci_p5")
            if rep.get("exec"):
                ins["exec_trade_share"] = {x["name"]: x["trade_share"] for x in rep["exec"]["members"]}
        else:
            ins = {"p5": (rep.get("search") or {}).get("p5")}
        return add(fid, firm, role, mem, rules, ins, "objective: fast (mean of P1,P2,P3,P5)" if fast else "")

    for f in FIRMS:
        reps = res["firms"][f]["reports"]
        from_report(f, "single", reps["single"], "p5_single", f"{f}:single")
        from_report(f, "best2", reps["best2"], "best2", f"{f}:best2")
        from_report(f, "pf", reps["portfolio"], "portfolio_ge3", f"{f}:pf")
        fr = res["fast_objective"]["firms"][f]["reports"]
        from_report(f, "fast_single", fr["single"], "fast_single", f"{f}:fast_single", True)
        from_report(f, "fast_pf", fr["portfolio"], "fast_portfolio", f"{f}:fast_pf", True)
    # Flex-ext reports (PP_FLEX_TAKE_EXT=1, the ES verification's corrected Flex grid: day_take up to 1,560 so a 2-day pass is reachable); absent for NQ
    for stem, mp in (("portfolio_lucid_flexext", {"single": ("fx_single", "flexext_single", False), "best2": ("fx_best2", "flexext_best2", False)}),
                     ("portfolio_lucid_flexextfast", {"best2": ("fxfast_best2", "flexext_fast_best2", True)})):
        if (OUT / f"{stem}.json").exists():
            fj = json.loads((OUT / f"{stem}.json").read_text())
            for lab, (nm, role, fast) in mp.items():
                from_report("lucid", lab, fj["reports"][lab], role, f"lucid:{nm}", fast)
    # extra singles referenced by the multi-account mixes (as reported + the Lucid-only re-fill)
    mixes = dict(res["multi_account"]["mixes"])
    lo = OUT / "portfolio_multi_lucidonly.json"
    lo_mixes = json.loads(lo.read_text())["mixes"] if lo.exists() else {}
    for n, m in list(mixes.items()) + list(lo_mixes.items()):
        for a in m["accounts"]:
            f, lab = a.split(":", 1)
            if lab.startswith("single:"):
                from_report(f, lab, res["firms"][f]["reports"][lab], "mix_single", a)
    # candidates.csv: speed singles + fast-pass (Apex: compliant rows only; the reported Apex sets above carry their flags)
    for f in FIRMS:
        rows = [r for k, r in b.cand_rows.items() if k[0] == f]

        def cand_member(r, rules_s, reg=False):
            mi, rules = parse_rules(rules_s)
            return [{"cfg": b.cfg(r["key"]) if reg else r["key"], "sess": r["sess"], "micros": mi}], rules

        def ok(r, rules_s):
            if f not in APEX:
                return True
            mem, rules = cand_member(r, rules_s)
            return not apex_flag_list(b, mem, rules)

        def best(keyf, rules_col, rowfilter=lambda r: True):
            cs = [r for r in rows if rowfilter(r) and fnum(r[keyf]) is not None and r[rules_col] and ok(r, r[rules_col])]
            return max(cs, key=lambda r: (fnum(r[keyf]), fnum(r["p5"], 0.0))) if cs else None
        spec = []
        r1 = best("sp1_p1", "sp1_rules")
        if r1 and fnum(r1["sp1_p1"]) > 0:
            spec.append(("speed_p1", r1, "sp1_rules", {"p1": fnum(r1["sp1_p1"]), "p5": fnum(r1["sp1_p5"]), "bust5": fnum(r1["sp1_bust5"]), "lift": fnum(r1["sp1_lift_p1"])}))
        r3 = best("sp3_p3", "sp3_rules")
        if r3:
            spec.append(("speed_p3", r3, "sp3_rules", {"p3": fnum(r3["sp3_p3"]), "p5": fnum(r3["sp3_p5"]), "bust5": fnum(r3["sp3_bust5"]), "lift": fnum(r3["sp3_lift_p3"])}))
        r5 = best("p5", "rules")
        if f in APEX and r5:
            spec.append(("p5_single_compliant", r5, "rules", None))
        rf = best("p5", "rules", lambda r: r["fastpass"] == "1")
        if rf:
            spec.append(("fastpass", rf, "rules", None))
        for role, r, col, ins in spec:
            mem, rules = cand_member(r, r[col], True)
            ins = ins or {"p1": fnum(r["p1"]), "p2": fnum(r["p2"]), "p3": fnum(r["p3"]), "p5": fnum(r["p5"]), "bust5": fnum(r["bust5"]),
                          "lift": fnum(r["lift_p5"])}
            ins = dict(ins, model=r["primary_model"], eod_p5=fnum(r["eod_p5"]), intraday_p5=fnum(r["intr_p5"]), wf_oos_p5=fnum(r["wf_oos_p5"]),
                       wf_oos_lift=fnum(r["wf_oos_lift"]), source="candidates.csv", flags=r["flags"])
            add(f"{f}:{role}", f, role, mem, rules, ins)
    # Apex PA MAE rule (open loss <= $750 at ~zero profit; share of trades that reach it at the finalist's size must be <= 2%): IN-SAMPLE check of every Apex
    # finalist member, written into the manifest (and flagged NONCOMPLIANT); the apex_compliant gate of the search only tested day_stop (ES verification 2026-10-01).
    for fid, fin in fins.items():
        if fin["firm"] not in APEX:
            continue
        diag = []
        for m in fin["members"]:
            tr = E.load(b.configs[m["cfg"]]["in_sample_src"])
            mk = E._sess_mask(tr, m["sess"])
            n = max(int(mk.sum()), 1)
            diag.append({"member": f"{m['cfg']}|{m['sess']}@{m['micros']}", "trades": int(mk.sum()),
                         "mae750_share": float((tr.mae[mk] * m["micros"] / 10.0 >= 750.0).sum() / n),
                         "stop_gt_2000_share": float((tr.risk[mk] * m["micros"] / 10.0 > 2000.0).sum() / n)})
        fin["apex_pa_insample"] = diag
        worst = max(d["mae750_share"] for d in diag)
        if worst > 0.02:
            fin["apex_flags"] = fin["apex_flags"] + [f"mae750_share_{worst:.2f}_NONCOMPLIANT"]
    return fins, res


def multi(res: dict, fins: dict) -> dict:
    alias = {a: k for k, v in fins.items() for a in [k] + v["aliases"]}
    out = {}
    lo = OUT / "portfolio_multi_lucidonly.json"
    allm = [(n, m) for n, m in res["multi_account"]["mixes"].items()] + ([("Lo" + n, m) for n, m in json.loads(lo.read_text())["mixes"].items()] if lo.exists() else [])
    for n, m in allm:
        out[n] = {"counts": m["counts"], "accounts": [alias[a] for a in m["accounts"]], "accounts_reported": m["accounts"],
                  "insample": {"primary_p_any5": m["primary"]["p_any5"], "ci": m["primary"]["ci_p_any5"], "eod": m["eod"]["p_any5"],
                               "realized": m["realized"]["p_any5"], "intraday": m["intraday"]["p_any5"], "by_day": m["primary"]["p_any_by_day"],
                               "total_eval_cost": m["primary"]["total_eval_cost"], "cost_per_funded": m["primary"]["cost_per_funded"],
                               "e_funded": m["primary"]["e_funded"]}}
    return out


def funded_finalists(b: Builder) -> OrderedDict:
    txt = (OUT / "funded_summary.md").read_text()
    rows = {}
    for r in csv.DictReader((OUT / "funded_candidates.csv").open()):
        if r["stage"] == "full":
            rows[(r["variant"], r["cid"])] = r
    out: OrderedDict = OrderedDict()
    var = None
    for ln in txt.splitlines():
        if ln.startswith("## "):
            nm = ln[3:].split("  (")[0].strip()
            var = VARIANT_NAMES.get(nm)
            continue
        m = re.match(r"^(\d+)\. (\S+)/tf(\d+)/(\w+) \[([^\]]+)\] (m\d+K\d+L\d+S\d+T\d+P\w+)", ln)
        if not (var and m):
            continue
        rank = int(m.group(1))
        if rank > 2:
            continue
        key, sess, cell = m.group(5), m.group(4), m.group(6)
        r = rows[(var, f"{key}|{sess}")]
        assert r["e40_stable_cell"].replace(" ", "") == cell, (var, key, cell, r["e40_stable_cell"])
        t = re.match(r"m(\d+)K(\d+)L(\d+)S(\d+)T(\d+)P(\w+)", cell).groups()
        pol = t[5] if t[5] == "max" else int(t[5])
        cfgk = b.cfg(key)
        ins = {k: fnum(r[k]) for k in ("p_pay_20", "p_pay_40", "p_pay_60", "med_days_first", "e_first_gross", "e_first_net", "e_cheque_if_paid", "e_net_40",
                                       "e_net_60", "p_bust_pre_first", "p_bust_any", "e40_ci_lo", "e40_ci_hi", "ctrl_e40", "lift_e40", "alt1_e40", "alt2_e40",
                                       "wf_oos_e_net_40", "wf_oos_p_pay_40", "wf_oos_p_pay_20", "wf_oos_e_net_60", "cut_share")}
        ins["model"], ins["alt1_model"], ins["alt2_model"] = r["model"], r["alt1_model"], r["alt2_model"]
        fid = f"{var}#{rank}"
        flags = []
        if var == "apex":
            c = b.configs[cfgk]
            prof = E.profile_from(c["fam"], dict(c["params"], tf=c["tf"]))
            fi = json.loads(E.PL.shared("family_inputs.json").read_text())
            dflt = {row[0]: row[2] for row in fi.get(c["fam"], []) if len(row) > 3}
            inputs = {**{a: v for a, v in dflt.items() if a in ("sq_type", "mode")}, **c["params"], "tgt_r": prof["tgt_r"]}
            flags = F.apex_flags(c["fam"], inputs, {"day_stop": int(t[3])}, fnum(r["cut_share"]))
        out[fid] = {"variant": var, "rank": rank, "role": "top_pick" if rank == 1 else "runner_up", "cid": f"{key}|{sess}", "cfg": cfgk, "sess": sess,
                    "micros": int(t[0]), "rules": {"day_take": int(t[1]), "day_lock": int(t[2]), "day_stop": int(t[3]), "max_day_tr": int(t[4])},
                    "policy": pol, "cell": cell, "apex_flags": flags, "insample": ins}
    assert len(out) == 10, list(out)
    # same-config 'eval + funded' headline picks (funded_headline.md ranks 1-2 per variant; ES): a distinct pick is added as '<variant>#h<rank>'
    hp = OUT / "funded_headline.md"
    if hp.exists():
        var = None
        for ln in hp.read_text().splitlines():
            if ln.startswith("## "):
                var = VARIANT_NAMES.get(ln[3:].split(" (eval fee")[0].strip())
                continue
            m = re.match(r"^- (\d+)\. (\S+)/tf(\d+)/(\w+) \[([^\]]+)\] .*? \| funded (m\d+K\d+L\d+S\d+T\d+P\w+) ", ln)
            if not (var and m) or int(m.group(1)) > 2:
                continue
            rank, key, sess, cell = int(m.group(1)), m.group(5), m.group(4), m.group(6)
            same = [k for k, v in out.items() if v["variant"] == var and v["cid"] == f"{key}|{sess}" and v["cell"] == cell]
            if same:
                out[same[0]].setdefault("headline_ranks", []).append(rank)
                continue
            r = rows[(var, f"{key}|{sess}")]
            assert r["e40_stable_cell"].replace(" ", "") == cell, (var, key, cell, r["e40_stable_cell"])
            t = re.match(r"m(\d+)K(\d+)L(\d+)S(\d+)T(\d+)P(\w+)", cell).groups()
            pol = t[5] if t[5] == "max" else int(t[5])
            cfgk = b.cfg(key)
            ins = {k: fnum(r[k]) for k in ("p_pay_20", "p_pay_40", "p_pay_60", "med_days_first", "e_first_gross", "e_first_net", "e_cheque_if_paid", "e_net_40",
                                           "e_net_60", "p_bust_pre_first", "p_bust_any", "e40_ci_lo", "e40_ci_hi", "ctrl_e40", "lift_e40", "alt1_e40", "alt2_e40",
                                           "wf_oos_e_net_40", "wf_oos_p_pay_40", "wf_oos_p_pay_20", "wf_oos_e_net_60", "cut_share")}
            ins["model"], ins["alt1_model"], ins["alt2_model"] = r["model"], r["alt1_model"], r["alt2_model"]
            flags = []
            if var == "apex":
                c = b.configs[cfgk]
                prof = E.profile_from(c["fam"], dict(c["params"], tf=c["tf"]))
                fi = json.loads(E.PL.shared("family_inputs.json").read_text())
                dflt = {row[0]: row[2] for row in fi.get(c["fam"], []) if len(row) > 3}
                inputs = {**{a: v for a, v in dflt.items() if a in ("sq_type", "mode")}, **c["params"], "tgt_r": prof["tgt_r"]}
                flags = F.apex_flags(c["fam"], inputs, {"day_stop": int(t[3])}, fnum(r["cut_share"]))
            out[f"{var}#h{rank}"] = {"variant": var, "rank": f"h{rank}", "role": "headline_pick" if rank == 1 else "headline_runner_up", "cid": f"{key}|{sess}",
                                     "cfg": cfgk, "sess": sess, "micros": int(t[0]),
                                     "rules": {"day_take": int(t[1]), "day_lock": int(t[2]), "day_stop": int(t[3]), "max_day_tr": int(t[4])},
                                     "policy": pol, "cell": cell, "apex_flags": flags, "insample": ins}
    return out


def build(end: str | None = None) -> dict:
    de, nsess, partial = data_end()
    end = end or de
    b = Builder(end)
    fins, res = finalists(b)
    fund = funded_finalists(b)
    mix = multi(res, fins)
    nd = [l.split(",")[0] for l in (E.PL.shared("news_days.csv")).read_text().splitlines()[1:] if l.strip()]
    ho_news = [d for d in nd if HO_START <= d <= end]
    man = OrderedDict()
    man["schema"] = 1
    man["pilot"] = E.PL.NAME
    man["root"] = E.ROOT
    man["frozen_at_et"] = dt.datetime.now(E.ET).isoformat(timespec="seconds")
    man["in_sample_window"] = "2021-09-22..2024-12-31 (data starts 2021-09-22)"
    man["holdout"] = {"start": HO_START, "end": end, "data_end": de, "sessions_with_archive_manifest": nsess, "partial_sessions": partial,
                      "news_available": True, "news_source": "news_days.csv (built from ONYX TRADING/research/data/ff_usd_red_raw.txt: FF red USD CPI / NFP / FOMC)",
                      "news_days_in_holdout": len(ho_news), "news_last": ho_news[-1] if ho_news else None,
                      "coverage_tool_note": ("homebase data_coverage 2026-10-01T01:35Z (last 30 sessions): NQ complete 25, partial 4 (2026-09-11, 09-22, 09-23, 09-25), missing 1 (2026-09-07 = US holiday)"
                                             if E.ROOT == "NQ" else "homebase data_coverage 2026-10-01T14:45Z (last 30 sessions): ES complete 27, partial 2 (2026-09-22 with 2.0 hole hours, 2026-09-25), missing 1 (2026-09-07 = US holiday)")}
    man["scoring"] = {"K_controls": 10, "boots": 2000, "block_eval": 20, "block_funded": 60, "seed": E.SEED, "H_eval": E.H_EVAL, "H_funded": F.H_LIFE,
                      "criterion_p5": HS.CRITERION, "models": list(E.MODELS), "primary": E.PRIMARY, "funded_variants": HS.VARIANTS, "funded_models": HS.MODELS_ALT,
                      "rolling_starts": "every session with a full horizon (5 sessions eval, 60 funded) on the holdout calendar (weekday archive sessions)",
                      "controls": "day-matched random runs re-run on the same 2025+ days; pool = the same exit-profile pool as in-sample, eval seed crc32(cid)%100000, funded seed crc32('fund|'+cid)",
                      "no_retuning": True}
    man["firms"] = {f: {"rules_id": E.firm_rules(f)[0], "primary": E.PRIMARY[f], "cap_micros": E.firm_rules(f)[1]["cap_micros"],
                        "eval_fee": E._fees().get(E.firm_rules(f)[0], {}).get("eval_fee"), "activation": E._fees().get(E.firm_rules(f)[0], {}).get("activation"),
                        "unconfirmed": f in APEX} for f in FIRMS}
    man["firm_insample_wf"] = {f: res["firms"][f].get("wf_reselect") for f in FIRMS}
    man["configs"] = b.configs
    man["controls"] = b.controls
    man["finalists"] = fins
    man["funded"] = fund
    man["multi_account"] = mix
    man["jobs"] = b.jobs()
    man["inputs_sha256"] = {str(E.PL.shared(n)): HS.sha256_file(E.PL.shared(n)) for n in ("fees.json", "news_days.csv")}
    for f in FIRMS:
        rid = E.firm_rules(f)[0]
        p = Path(E.PKG.__file__).parent / "rules" / f"{rid}.json"
        if p.exists():
            man["inputs_sha256"][str(p)] = HS.sha256_file(p)
    man["code_sha256"] = HS.code_hashes()
    man["other_code_sha256"] = {f: HS.sha256_file(CODE / f) for f in ("build_holdout_manifest.py", "lucid_only_mixes.py", "gen_drafts.py", "template.py", "hb.py", "pilot.py")}
    return man


def summary(man: dict) -> str:
    L = [f"holdout {man['holdout']['start']}..{man['holdout']['end']} (data end {man['holdout']['data_end']}, {man['holdout']['sessions_with_archive_manifest']} sessions, "
         f"partial {man['holdout']['partial_sessions']}); news days in holdout {man['holdout']['news_days_in_holdout']}"]
    jobs = man["jobs"]
    L.append(f"unique tester configs {len(man['configs'])} -> finalist runs {sum(1 for j in jobs if j['role'] == 'finalist')}, control runs {sum(1 for j in jobs if j['role'] == 'control')}, total jobs {len(jobs)}")
    L.append(f"eval finalists {len(man['finalists'])}; funded finalists {len(man['funded'])}; multi mixes {sorted(man['multi_account'])}")
    for fid, f in man["finalists"].items():
        L.append(f"  {fid:34s} {'+'.join(f['roles']):40s} {len(f['members'])}m {f['rules']} {'APEX-FLAGS ' + ','.join(f['apex_flags']) if f['apex_flags'] else ''}")
    for fid, f in man["funded"].items():
        L.append(f"  funded {fid:12s} {f['cid']} {f['cell']} {f['apex_flags'] or ''}")
    return "\n".join(L)


def main(argv):
    if "--jobs" in argv:
        man = json.loads(HS.MANIFEST.read_text())
        out = Path(argv[argv.index("--jobs") + 1])
        out.write_text("".join(json.dumps({k: v for k, v in j.items() if k not in ("role", "source_key")}) + "\n" for j in man["jobs"]))
        print("wrote", out, len(man["jobs"]), "job lines")
        return
    man = build()
    print(summary(man))
    if "--freeze" in argv:
        if HS.MANIFEST.exists():
            sys.exit("manifest already frozen; refusing to overwrite")
        HS.MANIFEST.write_text(json.dumps(man, indent=1, default=str))
        HS.SHA_FILE.write_text(HS.sha256_file(HS.MANIFEST) + "  holdout_manifest.json\n")
        print("FROZEN", HS.MANIFEST, HS.sha256_file(HS.MANIFEST))
    else:
        (OUT / "holdout_manifest.draft.json").write_text(json.dumps(man, indent=1, default=str))
        print("draft written (not frozen)")


if __name__ == "__main__":
    main(sys.argv[1:])
