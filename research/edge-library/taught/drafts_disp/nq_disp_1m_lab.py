"""NQ 1-minute displacement lab (owner, 2026-10-21): the candle break with three switchable ideas -- a 15-minute direction, a volatility-sized body, a volume burst.

Every signal is decided at a 1-minute candle's close from prints up to that close only (candles built in `scan` from the tape, ET clock).
THE 1-MINUTE TRIGGER: the candle closes beyond the previous candle's wick (above its high = long, below its low = short) and is big:
  trig = prev  its body |close - open| >= body_x x the previous candle's body
  trig = atr   its body >= atr_k x ATR(14) of the 14 one-minute candles before it (true range, simple mean)
SWITCHES (all off by default):
  htf = 15     #1: a 15-minute candle (ET clock, :00 :15 :30 :45) that closes beyond the previous 15-minute candle's wick with a body >=
               htf_body_x x the previous 15-minute body sets the direction for the next htf_win minutes; only 1-minute signals that way trade.
               A newer 15-minute signal replaces the old one.
  vol_x > 0    #3: the 1-minute candle's volume >= vol_x x the mean volume of the 20 one-minute candles before it.
Entries only for candles that open at or after w_start and close at or before w_end. Market entry at the close; stop = the candle's other
extreme (low for a long, high for a short); target = rr x that distance; both re-priced from the fill. No daily cap; one position at a
time; flat 15:58. Prints from 09:00 seed the previous candles, ATR, volume mean and the first 15-minute candles."""
from __future__ import annotations

from homebase.strategies.base import Input, Strategy

NS = 1_000_000_000
MIN = 60 * NS


def _sec(hhmm):
    p = [int(x) for x in hhmm.split(":")]
    return p[0] * 3600 + p[1] * 60 + (p[2] if len(p) > 2 else 0)


class NqDisp1mLab(Strategy):
    name = "NQ 1-minute displacement lab"
    root = "NQ"
    own_stop = True     # it passes its own sl (the candle extreme): the heat map gets the 4 own-stop rows (2026-10-21)
    session_window = ("09:00", "16:00")
    bar_minutes = 0
    session_independent = True

    @classmethod
    def inputs(cls):
        return [Input("trig", "1m size test", "choice", "prev", None, None, None, ("prev", "atr")),
                Input("body_x", "prev: body >= x previous body", "float", 2.0, 0.0, 10.0, 0.25),
                Input("atr_k", "atr: body >= k x ATR(14)", "float", 1.5, 0.1, 10.0, 0.25),
                Input("htf", "15-min direction", "choice", "off", None, None, None, ("off", "15")),
                Input("htf_body_x", "15-min body >= x previous", "float", 2.0, 0.0, 10.0, 0.25),
                Input("htf_win", "Direction lasts (min)", "int", 15, 1, 120, 1),
                Input("vol_x", "Volume >= x mean of 20 (0 = off)", "float", 0.0, 0.0, 10.0, 0.25),
                Input("rr", "Target (x the stop)", "float", 1.0, 0.1, 10.0, 0.25),
                Input("w_start", "First candle opens", "choice", "09:30", None, None, None, ("09:30", "09:45", "10:00")),
                Input("w_end", "Last candle closes", "choice", "15:00", None, None, None, ("09:35", "10:00", "11:00", "12:00", "15:00"))]

    def times(self):
        return ["15:58"]

    def scan(self, tape, lo, hi, t0, t1):
        p = self.p
        base = t0 - _sec("09:00") * NS                 # 00:00 ET of the session date
        first = base + _sec(p["w_start"]) * NS
        last = base + _sec(p["w_end"]) * NS
        bx, ak, vx, rr = float(p["body_x"]), float(p["atr_k"]), float(p["vol_x"]), float(p["rr"])
        use_atr, use_htf = p["trig"] == "atr", p["htf"] == "15"
        hbx, hwin = float(p["htf_body_x"]), int(p["htf_win"]) * MIN
        ts, px, sz = tape.ts, tape.px, tape.size
        out = []
        bars = []                                      # closed 1-minute candles: (start, o, h, l, c, v)
        q = []                                         # the 1-minute candles of the 15-minute candle being built
        h15 = None                                     # the previous 15-minute candle (o, h, l, c)
        bias, bias_until = 0, 0
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
                i += 1
            if c is not None:
                if bars and b0 >= first and b1 <= last:
                    _, po, ph, pl, pc, _ = bars[-1]
                    side = "long" if c > ph else ("short" if c < pl else None)
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
                    if ok and use_htf:
                        want = 1 if side == "long" else -1
                        ok = bias == want and b1 <= bias_until
                    if ok:
                        out.append((b1, (side, c, l if side == "long" else h)))
                bars.append((b0, o, h, l, c, v))
                q.append((b0, o, h, l, c))
            # a 15-minute candle ends on the ET clock's :00 / :15 / :30 / :45
            if ((b1 - base) // NS) % 900 == 0:
                if q:
                    co, ch = q[0][1], max(x[2] for x in q)
                    cl, cc = min(x[3] for x in q), q[-1][4]
                    if h15 is not None:
                        po, ph, pl, pc = h15
                        big = abs(cc - co) >= hbx * abs(pc - po)
                        if big and cc > ph:
                            bias, bias_until = 1, b1 + hwin
                        elif big and cc < pl:
                            bias, bias_until = -1, b1 + hwin
                    h15 = (co, ch, cl, cc)
                q = []
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
