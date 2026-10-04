"""Desk live path vs tester path: feed the day's RAW prints (add_tick, as the desk's market-data socket does) into
TickBars up to the fire, run levels.compute_geometry, compare with the geometry the tester run drew (hlines + ATR plot)."""
import sys, json, glob, datetime as dt, time
sys.path.insert(0, "."); 
from homebase.atrbars import TickBars, et_ms
from homebase.backtest.tape import TapeStore
from homebase.config import _defaults
from homebase.levels import compute_geometry
name, SP = sys.argv[1], sys.argv[2]
lim = int(sys.argv[3]) if len(sys.argv) > 3 else 10**9
cfg = _defaults().strategies[name]
run = sorted(glob.glob(f"{SP}/dm/base3/runs/*-{name}-*"))[-1]
pl = json.load(open(run + "/plots.json"))
hl = {}
for h in pl["hlines"]:
    hl.setdefault(h["date"], {})[h["name"]] = h["price"]
atr = {}
for t, v in pl["plots"]["ATR"]:
    atr[dt.datetime.fromtimestamp(t/1000, dt.timezone.utc).astimezone(__import__("zoneinfo").ZoneInfo("America/New_York")).date().isoformat()] = v
store = TapeStore()
tick = 0.25
bad, ok, t0 = [], 0, time.time()
for n, (d, h) in enumerate(sorted(hl.items())):
    if n >= lim: break
    day = dt.date.fromisoformat(d)
    tape = store.load("NQ", day)
    fire = et_ms(day, cfg.fire_et)
    tb = TickBars(day)
    ts, px, sz = tape.ts, tape.px, tape.size
    for i in range(len(ts)):
        m = ts[i] // 1_000_000
        if m >= fire: break
        tb.add_tick(m, px[i], sz[i])
    g, why = compute_geometry(cfg, tb, fire, tick)
    if g is None:
        bad.append((d, "geometry None: " + why)); continue
    chk = {"Long entry": g.upper, "Short entry": g.lower,
           "Long SL (planned)": g.upper - g.sl_pts, "Short SL (planned)": g.lower + g.sl_for("Sell")}
    if g.anchor is not None: chk["anchor"] = g.anchor
    else: chk["range high"], chk["range low"] = g.range_hi, g.range_lo
    diffs = {k: (v, h.get(k)) for k, v in chk.items() if h.get(k) is None or abs(v - h[k]) > 1e-9}
    if abs(g.atr - atr[d]) > 1e-9: diffs["ATR"] = (g.atr, atr[d])
    if diffs: bad.append((d, diffs))
    else: ok += 1
print(name, "days", ok + len(bad), "identical", ok, "different", len(bad), "secs", round(time.time() - t0))
for b in bad[:15]: print("  ", b)
json.dump({"name": name, "days": ok + len(bad), "identical": ok, "bad": bad}, open(f"{SP}/dm/tickfed_{name}.json", "w"))
