"""Verifier: the Template's LATE tf close (the last minute of a tf bucket has no print -> the bucket is closed, and the
family is asked, at the end of the next minute that has a print). Synthetic; which rows does the family read there?"""
import sys
sys.dont_write_bytecode = True
L = "/Users/ramoscapital/ramos-quant-homebase/research/prop-portfolio/2026-10-01-l2"
sys.path.insert(0, L); sys.path.insert(0, L + "/tests")
import numpy as np
import l2sim as S
import families.walls as W
import test_fam_walls as T

MIN, at, T0 = T.MIN, T.at, T.T0
reads = []
real = S.Ctx.feat
def spy(self, name, back=0, default=None):
    f, now = self._feat, self._s.now
    k = int(np.searchsorted(f.usable_ns, now, side="right")) - 1 - back
    assert back >= 0 and (k < 0 or f.usable_ns[k] <= now)
    reads.append((now, name, back, None if k < 0 else int(f.usable_ns[k])))
    return real(self, name, back, default)
S.Ctx.feat = spy

def go(cls, rows, prints, params=None):
    reads.clear()
    st = cls({"tf": "5", **(params or {})})
    res = S.run_session(st, T.tape(prints), features=T.table(rows))
    assert res.skip is None
    return st, res

# minute 4 (09:34) has NO print: the 09:30-09:35 bucket is closed at the bar of minute 5 (now = 09:36:00)
base = {4: []}
# (a) wall in row 5 (usable 09:36:00), last print 2 ticks in front at 09:36:00
st, res = go(T.Bounce, {5: T.bid_wall()}, {**base, 5: [100.50, 100.25]})
print("a) decisions (min after 09:30):", [(t - T0) / MIN for t, _ in st.seen][:4], "calls:", [((c["t"] - T0) / MIN, c["side"], c["px"], c["placed"]) for c in st.calls])
assert [c["t"] for c in st.calls] == [at(5)]
assert all(u <= now for now, _, _, u in reads if u is not None)
print("   rows read at the late close:", sorted({((now - T0) / MIN, (u - T0) / MIN) for now, n, b, u in reads if now == at(5)}))
# (b) wall ONLY in row 4 (usable 09:35:00; no decision there): must not be used at 09:36:00 (row 5 is the newest)
st, _ = go(T.Bounce, {4: T.bid_wall()}, {**base, 5: [100.50, 100.25]})
assert st.calls == [], st.calls
# (c) wall ONLY in row 6 (usable 09:37:00): nothing at 09:36:00
st, _ = go(T.Bounce, {6: T.bid_wall()}, {**base, 5: [100.50, 100.25], 6: [100.25]})
assert not [c for c in st.calls if c["t"] <= at(5)], st.calls
# (d) B5 at a late close: standing in rows 3, 4, gone in row 5, traded through
st, _ = go(T.Break, {3: T.STAND, 4: T.STAND, 5: T.GONE}, {**base, 5: [100.25, 99.75]})
print("d) break calls:", [((c["t"] - T0) / MIN, c["side"], c["px"]) for c in st.calls])
assert [c["t"] for c in st.calls] == [at(5)]
#     ... and gone only in row 6 (not usable at 09:36:00): nothing at the late close
st, _ = go(T.Break, {3: T.STAND, 4: T.STAND, 5: T.STAND, 6: T.GONE}, {**base, 5: [100.25, 99.75], 6: [99.75]})
assert not [c for c in st.calls if c["t"] <= at(5)], st.calls
# (e) normal on-grid tf 5 close (minute 9 has prints -> decision at 09:40:00 reads row 9, never row 10)
st, _ = go(T.Bounce, {10: T.bid_wall()}, {9: [100.50, 100.25], 10: [100.25]})
assert not [c for c in st.calls if c["t"] <= at(9)]
print("late-close checks ok; off-grid decision at 09:36:00 confirmed (no future row read)")
