"""NQ range break with the 1-minute displacement rule, any range of the day (owner, 2026-10-21): a range from r_start for orb_min minutes; a big 1-minute candle closing beyond it trades.

THE RANGE: the high and low of the prints [r_start, r_start + orb_min) on the ET clock of the trade date (00:00 .. 13:30).
THE TRIGGER, decided at a 1-minute candle's close (candles built in `scan` from the tape), for candles that open at or after the range
end and close at or before range end + w_len minutes (and 15:55 at the latest):
  long   the candle closes above the RANGE HIGH and above the previous 1-minute candle's high, and is big
  short  the candle closes below the RANGE LOW and below the previous 1-minute candle's low, and is big
  big:   trig = atr   its body |close - open| >= atr_k x ATR(14) of the 14 one-minute candles before it (true range, simple mean)
         trig = prev  its body >= body_x x the previous candle's body
  vol_x > 0: also the candle's volume >= vol_x x the mean volume of the 20 one-minute candles before it.
Market entry at the close; stop = the candle's other extreme (low for a long, high for a short); target = rr x that distance; both
re-priced from the fill. No daily cap; one position at a time; flat 15:58. Candles from 00:00 seed the ATR and the volume mean (a range
at 00:00 trades once 14 / 20 candles exist)."""
from __future__ import annotations

from homebase.strategies.base import Input, Strategy

NS = 1_000_000_000
MIN = 60 * NS


def _sec(hhmm):
    p = [int(x) for x in hhmm.split(":")]
    return p[0] * 3600 + p[1] * 60 + (p[2] if len(p) > 2 else 0)


class NqDispRangeLab(Strategy):
    name = "NQ range break + 1-minute displacement (any range)"
    root = "NQ"
    own_stop = True     # it passes its own sl (the candle extreme): the heat map gets the 4 own-stop rows (2026-10-21)
    session_window = ("00:00", "16:00")
    bar_minutes = 0
    session_independent = True

    @classmethod
    def inputs(cls):
        return [Input("r_start", "Range starts", "choice", "09:30", None, None, None,
                      ("00:00", "03:00", "08:00", "08:30", "09:30", "10:30", "12:00", "13:30")),
                Input("orb_min", "Range minutes", "choice", "15", None, None, None, ("5", "15", "30", "60")),
                Input("w_len", "Entries for (min) after the range", "choice", "120", None, None, None, ("30", "60", "120", "240", "330")),
                Input("trig", "1m size test", "choice", "atr", None, None, None, ("atr", "prev")),
                Input("atr_k", "atr: body >= k x ATR(14)", "float", 2.0, 0.1, 10.0, 0.25),
                Input("body_x", "prev: body >= x previous body", "float", 2.0, 0.0, 10.0, 0.25),
                Input("vol_x", "Volume >= x mean of 20 (0 = off)", "float", 0.0, 0.0, 10.0, 0.25),
                Input("rr", "Target (x the stop)", "float", 2.0, 0.1, 10.0, 0.25)]

    def times(self):
        return ["15:58"]

    def scan(self, tape, lo, hi, t0, t1):
        p = self.p
        base = t0                                      # session_window starts 00:00 ET of the trade date
        r0 = base + _sec(p["r_start"]) * NS
        r1 = r0 + int(p["orb_min"]) * MIN
        last = min(r1 + int(p["w_len"]) * MIN, base + _sec("15:55") * NS)
        bx, ak, vx = float(p["body_x"]), float(p["atr_k"]), float(p["vol_x"])
        use_atr = p["trig"] == "atr"
        ts, px, sz = tape.ts, tape.px, tape.size
        out = []
        bars = []                                      # closed 1-minute candles: (start, o, h, l, c, v)
        rh = rl = None                                 # the range
        i = lo
        b0 = max(t0, r0 - 30 * MIN)                     # 30 minutes before the range seed the ATR and volume mean
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
