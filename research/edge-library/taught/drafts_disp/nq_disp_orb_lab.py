"""NQ opening-range break with the 1-minute displacement rule (owner, 2026-10-21): the first 15 minutes are the range; a big 1-minute candle closing beyond it trades.

THE RANGE: the high and low of the prints 09:30 .. 09:30 + orb_min (15 by default).
THE TRIGGER, decided at a 1-minute candle's close (candles built in `scan` from the tape, ET clock), only after the range is complete:
  long   the candle closes above the RANGE HIGH and above the previous 1-minute candle's high, and is big
  short  the candle closes below the RANGE LOW and below the previous 1-minute candle's low, and is big
  big:   trig = atr   its body |close - open| >= atr_k x ATR(14) of the 14 one-minute candles before it (true range, simple mean)
         trig = prev  its body >= body_x x the previous candle's body
  vol_x > 0: also the candle's volume >= vol_x x the mean volume of the 20 one-minute candles before it.
Entries for candles that close at or before w_end. Market entry at the close; stop = the candle's other extreme (low for a long, high
for a short); target = rr x that distance; both re-priced from the fill. No daily cap; one position at a time; flat 15:58.
Prints from 09:00 seed the ATR and the volume mean."""
from __future__ import annotations

from homebase.strategies.base import Input, Strategy

NS = 1_000_000_000
MIN = 60 * NS


def _sec(hhmm):
    p = [int(x) for x in hhmm.split(":")]
    return p[0] * 3600 + p[1] * 60 + (p[2] if len(p) > 2 else 0)


class NqDispOrbLab(Strategy):
    name = "NQ opening-range break + 1-minute displacement"
    root = "NQ"
    own_stop = True     # it passes its own sl (the candle extreme): the heat map gets the 4 own-stop rows (2026-10-21)
    session_window = ("09:00", "16:00")
    bar_minutes = 0
    session_independent = True

    @classmethod
    def inputs(cls):
        return [Input("orb_min", "Range minutes from 09:30", "choice", "15", None, None, None, ("5", "15", "30")),
                Input("trig", "1m size test", "choice", "atr", None, None, None, ("atr", "prev")),
                Input("atr_k", "atr: body >= k x ATR(14)", "float", 2.0, 0.1, 10.0, 0.25),
                Input("body_x", "prev: body >= x previous body", "float", 2.0, 0.0, 10.0, 0.25),
                Input("vol_x", "Volume >= x mean of 20 (0 = off)", "float", 0.0, 0.0, 10.0, 0.25),
                Input("rr", "Target (x the stop)", "float", 1.0, 0.1, 10.0, 0.25),
                Input("w_end", "Last candle closes", "choice", "15:00", None, None, None, ("10:00", "11:00", "12:00", "15:00"))]

    def times(self):
        return ["15:58"]

    def scan(self, tape, lo, hi, t0, t1):
        p = self.p
        base = t0 - _sec("09:00") * NS                 # 00:00 ET of the session date
        r0 = base + _sec("09:30") * NS
        r1 = r0 + int(p["orb_min"]) * MIN
        last = base + _sec(p["w_end"]) * NS
        bx, ak, vx = float(p["body_x"]), float(p["atr_k"]), float(p["vol_x"])
        use_atr = p["trig"] == "atr"
        ts, px, sz = tape.ts, tape.px, tape.size
        out = []
        bars = []                                      # closed 1-minute candles: (start, o, h, l, c, v)
        rh = rl = None                                 # the opening range
        i = lo
        b0 = t0
        while i < hi and ts[i] < b0:
            i += 1
        while b0 < last:
            b1 = b0 + MIN
            o = h = l = c = None
            v = 0.0
            while i < hi and ts[i] < b1:
                x = px[i]
                if o is None:
                    o = x
                h = x if h is None or x > h else h
                l = x if l is None or x < l else l
                c = x
                v += float(sz[i])
                if r0 <= ts[i] < r1:
                    rh = x if rh is None or x > rh else rh
                    rl = x if rl is None or x < rl else rl
                i += 1
            if c is not None:
                if bars and b0 >= r1 and rh is not None:
                    _, po, ph, pl, pc, _ = bars[-1]
                    side = "long" if (c > ph and c > rh) else ("short" if (c < pl and c < rl) else None)
                    ok = side is not None
                    if ok and use_atr:
                        prior = bars[-14:]
                        if len(prior) < 14:
                            ok = False
                        else:
                            trs, prev_c = [], None
                            for (_, bo, bh, bl, bc, _) in prior:
                                trs.append(bh - bl if prev_c is None else max(bh, prev_c) - min(bl, prev_c))
                                prev_c = bc
                            ok = abs(c - o) >= ak * (sum(trs) / 14.0)
                    elif ok:
                        ok = abs(c - o) >= bx * abs(pc - po)
                    if ok and vx > 0:
                        prior = bars[-20:]
                        ok = len(prior) == 20 and v >= vx * (sum(b[5] for b in prior) / 20.0)
                    if ok:
                        out.append((b1, (side, c, l if side == "long" else h)))
                bars.append((b0, o, h, l, c, v))
            b0 = b1
        return out

    def on_session(self, ctx):
        pass

    def on_signal(self, ctx, sig):
        side, ref, ext = sig
        if not ctx.flat:
            return
        risk = (ref - ext) if side == "long" else (ext - ref)
        if risk <= 0:
            ctx.skip("signal candle has no range on the stop side")
            return
        rr = float(self.p["rr"])
        tp = ref + rr * risk if side == "long" else ref - rr * risk
        ctx.move_brackets_to_fill = True
        ctx.market(side, sl=ext, tp=tp, ref=ref)

    def on_time(self, ctx, et_time):
        if et_time == "15:58":
            ctx.flatten("time")
