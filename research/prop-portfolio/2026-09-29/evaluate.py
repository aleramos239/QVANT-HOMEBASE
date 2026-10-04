#!/usr/bin/python3
"""CLI: exact P(pass <= 5d) for one config. Needs numpy: run with /usr/bin/python3.

  evaluate.py RUN[:sess[:micros]] [RUN2[:sess[:micros]] ...] [--day-stop Y] [--day-lock X] [--max-day-tr N]
              [--after-loss M] [--after-win M] [--target-stop] [--day-take X] [--target-take] [--firm lucid|apex|both] [--tag T]
              [--news skip|only] [--mc 10000] [--boots 2000] [--eventual 2000] [--no-funded]
  evaluate.py --cfg config.json [--tag T]

RUN = run id, 'grid_id#cell', or a path to trades.json. Writes R/out/<tag>.json, prints one summary line."""
import argparse
import json
import sys

import evalcore as E


def member(s: str, news: str) -> dict:
    p = s.split(":")
    return {"src": p[0], "sess": p[1] if len(p) > 1 and p[1] else "all",
            "micros": int(p[2]) if len(p) > 2 else 10, "news": news}


def main(argv=None):
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("members", nargs="*")
    a.add_argument("--cfg")
    a.add_argument("--tag")
    a.add_argument("--firm", default="both")
    a.add_argument("--news", default="all")
    a.add_argument("--day-stop", type=float, default=0)
    a.add_argument("--day-lock", type=float, default=0)
    a.add_argument("--max-day-tr", type=int, default=0)
    a.add_argument("--after-loss", type=float, default=1.0)
    a.add_argument("--after-win", type=float, default=1.0)
    a.add_argument("--target-stop", action="store_true")
    a.add_argument("--day-take", type=float, default=0)
    a.add_argument("--target-take", action="store_true")
    a.add_argument("--mc", type=int, default=10000)
    a.add_argument("--boots", type=int, default=2000)
    a.add_argument("--eventual", type=int, default=2000)
    a.add_argument("--no-funded", action="store_true")
    a.add_argument("--start")
    a.add_argument("--end")
    a = a.parse_args(argv)
    if a.cfg:
        cfg = json.load(open(a.cfg))
    else:
        cfg = {"members": [member(m, a.news) for m in a.members],
               "rules": {"day_stop": a.day_stop, "day_lock": a.day_lock, "max_day_tr": a.max_day_tr,
                         "after_loss": a.after_loss, "after_win": a.after_win, "target_stop": a.target_stop,
                         "day_take": a.day_take, "target_take": a.target_take}}
        if a.firm != "both":
            cfg["firms"] = [a.firm]
    for k in ("tag", "start", "end"):
        if getattr(a, k):
            cfg[k] = getattr(a, k)
    if not cfg.get("members"):
        sys.exit("no members")
    res = E.evaluate(cfg, mc=a.mc, boots=a.boots, eventual=a.eventual, funded=not a.no_funded)
    E.save(res)
    print(E.line(res) if "firms" in res and res["firms"] else res.get("skipped"))


if __name__ == "__main__":
    main()
