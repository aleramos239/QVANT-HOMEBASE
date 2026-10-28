"""The two fvg_tap_disp in-sample heat maps on one page, with the 2026-10-26 page maker. Run from research/edge-library."""
import json, sys, importlib.util
from pathlib import Path
import types
src = Path("out/daily_ideas_heatmaps_2026-10-26/make.py").read_text().replace("idea\\'s own stop", "idea&#39;s own stop")   # py3.9: no backslash in f-strings
hm = types.ModuleType("hm"); hm.__file__ = "make.py"; exec(compile(src, "daily_make.py", "exec"), hm.__dict__)
OUT = Path("out/fvg_tap_disp_heatmaps_2026-10-27")
NAMES = tuple(sys.argv[2:]) or ("nq_fvg15_tap_disp_out", "nq_fvg15_tap_disp_in")
PAGE = sys.argv[1] if len(sys.argv) > 1 else "index.html"
hm.SPECS = {n: json.load(open(Path.home() / f".homebase/ideas/{n}/spec.json")) for n in NAMES}
TXT = {"out": "the 1-minute candle must CLOSE BEYOND the gap (above a bullish gap, below a bearish one)",
       "in": "the 1-minute candle may close INSIDE the gap or beyond it"}
DISP = {"atr": "body at least k x the 1-minute ATR, k = 1 / 1.5 / 2",
        "wick": "it closes past the previous 1-minute candle's wick and its body is at least k x the previous candle's body, k = 1.5 / 2 / 3"}
old = hm.explain
hm.explain = lambda name, sp: (
    f"{sp['run']['fixed'].get('gtf', 15)}-minute fair value gaps (overnight ones count). Price taps into a live gap on the {sp['home']['bar'] if 'home' in sp else sp['card']['home']['bar']}-minute chart; then a {sp['card']['home']['bar']}-minute displacement candle "
    f"({DISP[sp['run']['fixed'].get('disp', 'atr')]}) pushes back the gap's way and {TXT[sp['run']['fixed']['close']]} -> market entry with the gap. "
    f"A gap-size candle that closes through the gap (inversion) kills it: no trade. Own stop = the low (high) of the tap. Each gap trades once; "
    f"entries {sp['run']['fixed'].get('start', '09:30')}-15:00 ET, up to 3 a day, flat 15:58." if sp["run"]["family"] == "fvg_tap_disp" else old(name, sp))
items = [hm.analyse(n) for n in NAMES]
body = "".join(hm.page(a) for a in items)
HEAD = ("<h1>15-min FVG tap + 1-min displacement: both heat maps</h1>" + f"<div class=sub>Displacement: {DISP[hm.SPECS[NAMES[0]]['run']['fixed'].get('disp', 'atr')]}.</div>"
        + "<div class=sub>Top: displacement must close beyond the gap. Bottom: may close inside it. hm40, 3:1 in-sample months only, 1 NQ. Test months not read, nothing picked.</div>"
        ) if len(NAMES) == 2 else ("<h1>FVG tap + displacement: no window (entries 00:00-15:00, flat 15:58)</h1>"
        + "<div class=sub>Four heat maps: ATR displacement (out, in), then wick displacement (out, in). Gap size and trade bar are in each title. hm40, 3:1 in-sample months only, 1 NQ. Test months not read, nothing picked.</div>")
(OUT / PAGE).write_text(hm.wrap(HEAD + body, "fvg tap disp heat maps"))
print({a["name"]: (a["summ"]["green"], a["summ"]["net"]) for a in items}, (OUT / PAGE).stat().st_size)
