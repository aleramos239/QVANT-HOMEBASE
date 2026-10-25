import sys, json, numpy as np
sys.path.insert(0, '.')
from combo import load, daily
W = "/Users/ramoscapital/ramos-quant-homebase/research/edge-library"
sys.path[:0] = [W, W + "/engine"]
import l2sim as S
days = [d.toordinal() for d in S.sessions(*S.period(S.ALLOW_BP), "NQ", allow_holdout=S.ALLOW_BP)]
out = {"days": days}
for name in sys.argv[1:]:
    _, x = load(name); out[name] = daily(x, days).tolist()
json.dump(out, open("daily_series.json", "w"))
print(len(days), list(out)[1:])
