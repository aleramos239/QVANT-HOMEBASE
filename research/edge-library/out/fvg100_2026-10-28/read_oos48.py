import json, subprocess, sys
PY = "/Users/ramoscapital/ramos-quant-homebase/.venv-research/bin/python"
boxes = json.load(open("out/fvg100_2026-10-28/oos_boxes_48.json"))
rows = []
for t, n, box in boxes:
    tf = "15" if n.endswith("15") else "5"
    store = "f100_%s-NQ-tf%s__%s" % (n, tf, box)
    out = subprocess.run([PY, "bp.py", "wf", "show", store, "--json"], capture_output=True, text=True).stdout
    w = json.loads(out)["wf"]
    ins = [b for b in w["is"] if b["box"] == box][0]
    o = w["oos"]["record"]; bl = w["oos"]["blocks"]
    rows.append(dict(idea=n, box=box, tf=tf, is_t=ins["t_stat"], is_avg=ins["avg_trade"], is_n=ins["trades"], is_net=ins["net"],
        o_n=o["trades"], o_avg=o["avg_trade"], o_net=o["net"], o_t=o["t_stat"], o_wr=o["win_rate"], o_be=o["breakeven"], o_pf=o["pf"],
        blk_pos=sum(1 for b in bl if b["net"] > 0), blk_n=len(bl), long=o["long_net"], short=o["short_net"]))
json.dump(rows, open("out/fvg100_2026-10-28/oos_rows48.json", "w"))
print("idea box | IS tr avg t | OOS tr avg net t | blocks+ | pace")
for r in rows:
    print("%-7s %-22s | %4d %5.0f %4.1f | %4d %5.0f %7.0f %5.2f | %2d/%d | %4.0f%% L%+.0f S%+.0f" % (r["idea"], r["box"], r["is_n"], r["is_avg"], r["is_t"], r["o_n"], r["o_avg"], r["o_net"], r["o_t"] or 0, r["blk_pos"], r["blk_n"], 100*r["o_avg"]/r["is_avg"] if r["is_avg"] else 0, r["long"] or 0, r["short"] or 0))
