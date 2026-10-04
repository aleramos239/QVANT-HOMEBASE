"""ADVERSARIAL look-ahead verification of the flow group F1-F4 (families/flow.py). Verifier's own test, not in the suite.
Run:  cd <L> && python -B -m pytest out/verify/flow_lookahead/verify_flow.py -s -p no:cacheprovider
Real in-sample days (10, one process). No P&L is printed or asserted on.

  1. GARBAGE AFTER A CUT: every feature row not yet usable at the cut and every print stamped >= the cut is replaced by
     garbage (loud / random / removed). Every decision taken at or before the cut, every trade closed before it and the
     entry of every trade opened before it must be bit-identical to the clean run.
  2. POWER of 1: the same comparison must FAIL on a table whose flow values sit one minute early.
  3. POWER of the family: that +1 minute table changes the family's signals; garbage in the row that becomes usable
     exactly AT the cut changes the decision at the cut (the newest row is really read).
  4. ORACLE, causal by construction: the four definitions re-implemented from the raw tape and the raw feature rows,
     slicing explicitly by time (prints < T, rows stamped <= T - 60 s). Signal for signal equal on the real days.
  5. DATA: the flow columns of row M are recomputed from the tape's prints of [M, M + 60 s) only, and from a tape
     truncated at T for the minutes before T.
"""
import datetime as dt
import sys
import zlib
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import harness as H  # noqa: E402

S, NS = H.S, H.NS
CELLS = [(n, tf) for n in H.FAMS for tf in H.TFS]
ET = ZoneInfo("America/New_York")


def _window():
    if S.compute_window_end() is not None:
        pytest.skip("offline compute window")


def midnight_ns(d):
    return int(dt.datetime(d.year, d.month, d.day, tzinfo=ET).timestamp()) * NS


def pick_cuts(d, logs, rng, n_sig=12, n_rand=12):
    """Cut instants: up to n_sig instants where a signal fired in the clean runs (the cut IS the decision time), the same
    instants + 1 s for a few, and n_rand random instants of the day (on and off the minute grid)."""
    t0 = midnight_ns(d)
    hits = sorted({x["now"] for lg in logs for x in lg if x["hit"] is not None})
    if len(hits) > n_sig:
        hits = [hits[i] for i in np.linspace(0, len(hits) - 1, n_sig).astype(int)]
    out = list(hits) + [h + NS for h in hits[:3]]
    secs = rng.integers(5 * 60, 15 * 3600 + 55 * 60, n_rand)
    for j, s in enumerate(secs):
        s = int(s)
        if j % 3 == 0:
            s -= s % 300                                    # on the tf-5 grid
        elif j % 3 == 1:
            s -= s % 60                                     # on the minute grid
        out.append(t0 + s * NS + (0 if j % 3 != 2 else int(rng.integers(1, 10 ** 9))))
    return sorted(set(out))


# ------------------------------------------------------------------------------------------------ 1. garbage after a cut
@pytest.mark.parametrize("name,tf", CELLS)
def test_garbage_after_the_cut_never_changes_what_was_decided_before_it(name, tf):
    _window()
    n_dec = n_sig = n_tr = n_cmp = 0
    for iso in H.DAYS:
        d, tape, feats, _ = H.day_data(iso)
        base_flat = H.play(name, tf, iso, flat=True)
        base_real = H.play(name, tf, iso, flat=False)
        n_dec += len(base_flat[0])
        n_sig += sum(x["hit"] is not None for x in base_flat[0])
        n_tr += len(base_real[1])
        rng = np.random.default_rng(zlib.crc32(f"{name}{tf}{iso}".encode()))
        for j, cut in enumerate(pick_cuts(d, (base_flat[0], base_real[0]), rng)):
            gt = H.garbage_tape(tape, cut, rng)
            for mode in ("loud+" if j % 2 else "loud-", "random", "cut"):
                gf = H.garbage_feats(feats, cut, rng, mode)
                for flat, base in ((True, base_flat), (False, base_real)):
                    test = H.play(name, tf, iso, flat=flat, tape=gt, feats=gf)
                    bad = H.compare(base, test, cut)
                    assert not bad, (name, tf, iso, cut, mode, flat, bad[0][0], bad[0][1][-2:], bad[0][2][-2:])
                    n_cmp += 1
    print(f"\n[garbage {name} tf{tf}] days {len(H.DAYS)} decisions {n_dec} signals {n_sig} trades {n_tr} "
          f"garbage runs compared {n_cmp}: 0 differences before the cut")
    assert n_dec >= 1000 and n_sig >= 10 and n_tr >= 5          # not vacuous


# ------------------------------------------------------------------------------------------------ 2. power of the check
@pytest.mark.parametrize("name,tf", CELLS)
def test_power_the_garbage_check_catches_a_one_minute_leak(name, tf):
    """Flow values one minute early (row M shows minute M + 1): garbage in the rows not yet usable at the cut now reaches
    the decision AT the cut. The comparison must flag it."""
    _window()
    caught = total = 0
    for iso in H.DAYS:
        d, tape, feats, _ = H.day_data(iso)
        leaky = H.leak_plus_1min(feats)
        base = H.play(name, tf, iso, flat=True, feats=leaky)
        # cuts = decision instants of the leaky run where the price side of the trigger can fire
        cand = [x["now"] for x in base[0] if x["now"] % (int(tf) * 60 * NS) == 0 and (name != "cvd_div" or x["ext"] != 0)]
        if len(cand) > 10:
            cand = [cand[i] for i in np.linspace(0, len(cand) - 1, 10).astype(int)]
        for cut in cand:
            rng = np.random.default_rng(zlib.crc32(f"{name}{tf}{iso}{cut}".encode()))
            gt = H.garbage_tape(tape, cut, rng)
            hit = False
            for mode in ("loud+", "loud-"):
                test = H.play(name, tf, iso, flat=True, tape=gt, feats=H.leak_plus_1min(H.garbage_feats(feats, cut, rng, mode)))
                hit |= bool(H.compare(base, test, cut))
            total += 1
            caught += hit
    print(f"\n[power/leak {name} tf{tf}] one-minute leak flagged at {caught} of {total} cuts")
    assert total >= 10 and caught >= max(3, total // 10)


# ------------------------------------------------------------------------------------------------ 3. power of the family
@pytest.mark.parametrize("name,tf", CELLS)
def test_power_plus_one_minute_shift_changes_the_family_output(name, tf):
    _window()
    days_changed = n_base = n_leak = n_diff = 0
    for iso in H.DAYS:
        _, _, feats, _ = H.day_data(iso)
        a = {(x["now"], x["hit"]) for x in H.play(name, tf, iso, flat=True)[0] if x["hit"] is not None}
        b = {(x["now"], x["hit"]) for x in H.play(name, tf, iso, flat=True, feats=H.leak_plus_1min(feats))[0]
             if x["hit"] is not None}
        n_base += len(a)
        n_leak += len(b)
        n_diff += len(a ^ b)
        days_changed += a != b
    print(f"\n[power/shift {name} tf{tf}] signals clean {n_base}, with flow values one minute early {n_leak}, "
          f"symmetric difference {n_diff}, days changed {days_changed} of {len(H.DAYS)}")
    assert days_changed >= 7 and n_diff >= 10         # 9 of the 10 days can signal (one is a roll day)


@pytest.mark.parametrize("name,tf", CELLS)
def test_power_the_newest_usable_row_is_really_read(name, tf):
    """Garbage that INCLUDES the row becoming usable exactly at the cut (usable_ns == cut) must change decisions at the cut."""
    _window()
    changed = total = 0
    for iso in H.DAYS:
        d, tape, feats, _ = H.day_data(iso)
        base = H.play(name, tf, iso, flat=True)
        cand = [x["now"] for x in base[0] if x["now"] % (int(tf) * 60 * NS) == 0 and (name != "cvd_div" or x["ext"] != 0)]
        if len(cand) > 10:
            cand = [cand[i] for i in np.linspace(0, len(cand) - 1, 10).astype(int)]
        for cut in cand:
            rng = np.random.default_rng(zlib.crc32(f"n{name}{tf}{iso}{cut}".encode()))
            hit = False
            for mode in ("loud+", "loud-"):
                test = H.play(name, tf, iso, flat=True, feats=H.garbage_feats(feats, cut, rng, mode, side="left"))
                a = [x for x in base[0] if x["now"] == cut]
                b = [x for x in test[0] if x["now"] == cut]
                hit |= a != b
                # ... and still nothing before the cut
                assert [x for x in base[0] if x["now"] < cut] == [x for x in test[0] if x["now"] < cut]
            total += 1
            changed += hit
    print(f"\n[power/newest {name} tf{tf}] decision at the cut changed at {changed} of {total} cuts")
    assert total >= 10 and changed >= max(3, total // 10)


def test_a_table_usable_one_minute_early_is_silenced_by_the_freshness_rule():
    """usable_ns one minute early (the forming minute visible): the families' own t_utc + 60 == T rule gives zero signals."""
    _window()
    for name, tf in CELLS:
        n = 0
        for iso in H.DAYS[:4]:
            _, _, f, _ = H.day_data(iso)
            early = S.Features(f.usable_ns - 60 * NS, f.cols)
            n += sum(x["hit"] is not None for x in H.play(name, tf, iso, flat=True, feats=early)[0])
        assert n == 0, (name, tf, n)


# ------------------------------------------------------------------------------------------------ 4. causal oracle
SESS = {"asia": (0, 10800), "london": (10800, 30300), "nyam": (34200, 39600), "mid": (39600, 48600), "pm": (48600, 57480)}
HALF_DAYS = {"2023-11-24"}
LOOK, MINV = 60, 30


def oracle(name, tf, iso):
    """Signals [(T_ns, side)] from the definitions in FAMILIES.md, reading ONLY prints stamped < T and feature rows
    stamped <= T - 60 s (explicit slices at every T)."""
    d, tape, feats, _ = H.day_data(iso)
    tf = int(tf)
    t0 = midnight_ns(d)
    end_s = (13 * 3600 + 15 * 60) if iso in HALF_DAYS else (16 * 3600 + 10 * 60)
    ts, px = tape.ts, tape.px
    step = tf * 60 * NS
    tu = feats.cols["t_utc"]
    assert (feats.usable_ns == (tu + 60) * NS).all()                 # the real table: usable_at = stamp + 60 s
    assert (np.diff(tu) > 0).all()
    fd, sb, ss, bok = (feats.cols[c] for c in ("f_delta", "f_sweep_buy_vol", "f_sweep_sell_vol", "book_ok"))
    i_lo = int(np.searchsorted(ts, t0, "left"))
    bars, tr_list, atr = [], [], None                                # tf bars with prints, closed so far: (end_ns, o, h, l, c)
    out = []
    k_first = t0 // step
    T = (k_first + 1) * step
    while T < t0 + end_s * NS:
        a, b = int(np.searchsorted(ts, T - step, "left")), int(np.searchsorted(ts, T, "left"))
        a = max(a, i_lo)
        if b > a:                                                    # the bucket [T - step, T) has prints (all < T)
            seg = px[a:b]
            o, h, l, c = float(seg[0]), float(seg.max()), float(seg.min()), float(seg[-1])
            tr = h - l if not bars else max(h - l, abs(h - bars[-1][4]), abs(l - bars[-1][4]))
            tr_list.append(tr)
            n = len(tr_list)
            atr = sum(tr_list) / n if n <= 14 else (atr * 13.0 + tr) / 14.0
            bars.append((T, o, h, l, c))
        sec = (T - t0) // NS
        Ts = T // NS
        T_next = T + step
        sid = next((s for s, (x, y) in SESS.items() if x < sec < y - 300), None)
        on_time = b > a and int(np.searchsorted(ts, T - 60 * NS, "left")) < b      # the bar's last minute printed
        if sid is None or not on_time or len(bars) < 3 or sec >= end_s - 300:
            T = T_next
            continue
        r = int(np.searchsorted(tu, Ts - 60, "left"))                # the row stamped T - 60 s
        if r >= len(tu) or tu[r] != Ts - 60 or not bok[r]:
            T = T_next
            continue
        vis = slice(0, r + 1)                                        # rows stamped <= T - 60 s: all a decision may see
        tv = tu[vis]
        _, o, h, l, c = bars[-1]
        side = None
        if name in ("delta_follow", "absorption", "sweep_follow"):
            cols = (fd[vis],) if name != "sweep_follow" else (sb[vis], ss[vis])
            sums, valid = [], []
            for j in range(LOOK + 1):
                m = (tv >= Ts - (j + 1) * tf * 60) & (tv < Ts - j * tf * 60)
                for cc in cols:
                    m = m & np.isfinite(cc)
                valid.append(bool(m.any()))
                sums.append([float(np.asarray(cc[m], np.float64).sum()) for cc in cols])
            if valid[0]:
                cur = abs(sums[0][0]) if name != "sweep_follow" else sums[0][0] + sums[0][1]
                hist = [abs(sums[j][0]) if name != "sweep_follow" else sums[j][0] + sums[j][1]
                        for j in range(1, LOOK + 1) if valid[j]]
                q = 95.0 if name == "sweep_follow" else 90.0
                if len(hist) >= MINV and cur > 0 and cur >= np.percentile(np.asarray(hist, np.float64), q):
                    if name == "delta_follow":
                        dd = sums[0][0]
                        side = "long" if dd > 0 and c > o else "short" if dd < 0 and c < o else None
                    elif name == "absorption":
                        if abs(c - o) <= 0.25 * atr:
                            side = "short" if sums[0][0] > 0 else "long"
                    else:
                        vb, vs = sums[0]
                        side = "long" if vb > vs else "short" if vs > vb else None
        else:                                                        # cvd_div
            s0 = t0 // NS + SESS[sid][0]
            m = (Ts - s0) // 60
            sess_bars = [x for x in bars if s0 * NS < x[0] <= T]     # tf bars whose close is inside the session so far
            if m >= 15 and len(sess_bars) >= 2:
                sel = (tv >= s0) & (tv < Ts)
                dv = np.asarray(fd[vis][sel], np.float64)
                if int(sel.sum()) == m and np.isfinite(dv[-1]):       # one row per session minute, newest delta finite
                    cum = np.cumsum(np.where(np.isfinite(dv), dv, 0.0))
                    cvd, x_hi, x_lo = cum[-1], max(0.0, cum.max()), min(0.0, cum.min())
                    h_prev = max(x[2] for x in sess_bars[:-1])
                    l_prev = min(x[3] for x in sess_bars[:-1])
                    if c > h_prev:
                        side = "short" if cvd < x_hi else None
                    elif c < l_prev:
                        side = "long" if cvd > x_lo else None
        if side:
            out.append((T, side))
        T = T_next
    return out


@pytest.mark.parametrize("name,tf", CELLS)
def test_a_causal_by_construction_oracle_reproduces_every_signal_on_real_days(name, tf):
    _window()
    n = 0
    for iso in H.DAYS:
        fam = [(x["now"], x["hit"][0]) for x in H.play(name, tf, iso, flat=True)[0] if x["hit"] is not None]
        orc = oracle(name, tf, iso)
        assert fam == orc, (name, tf, iso, sorted(set(fam) ^ set(orc))[:6], len(fam), len(orc))
        n += len(fam)
    print(f"\n[oracle {name} tf{tf}] {n} signals on {len(H.DAYS)} real days: identical to the causal oracle")
    assert n >= 10


# ------------------------------------------------------------------------------------------------ 5. the flow columns
def flow_minutes(ts, px, size):
    """Own re-implementation of the flow layer's per-minute delta / sweep volumes (orders = identical ts_ns; a sweep is
    signed by its own walk, a single-level order by the tick rule against the previous order, zero ticks carry the last
    sign). Reads the prints it is given, nothing else. -> {minute_utc_s: (delta, sweep_buy, sweep_sell, volume)}"""
    if len(ts) == 0:
        return {}
    new = np.r_[True, ts[1:] != ts[:-1]]
    st = np.flatnonzero(new)
    en = np.r_[st[1:], len(px)] - 1
    p0, p1 = px[st], px[en]
    lo, hi = np.minimum.reduceat(px, st), np.maximum.reduceat(px, st)
    sweep = hi > lo
    prev_last = np.r_[p0[0], p1[:-1]]
    g = np.where(sweep, np.sign(p1 - p0), np.sign(p0 - prev_last))
    last = 0.0
    for i in range(len(g)):                                          # carry the last non-zero sign forward
        if g[i] == 0:
            g[i] = last
        else:
            last = g[i]
    osz = np.add.reduceat(size, st).astype(np.float64)
    m = (ts[st] // (60 * NS)) * 60
    out = {}
    for mm in np.unique(m):
        k = m == mm
        out[int(mm)] = (float((g[k] * osz[k]).sum()), float(osz[k & sweep & (g > 0)].sum()),
                        float(osz[k & sweep & (g < 0)].sum()), float(osz[k].sum()))
    return out


def test_flow_rows_hold_only_their_own_minute_and_are_reproducible_from_a_truncated_tape():
    _window()
    cols = ("f_delta", "f_sweep_buy_vol", "f_sweep_sell_vol", "f_volume", "t_utc")
    n_rows = n_trunc = 0
    for iso in H.DAYS:
        d = dt.date.fromisoformat(iso)
        tape = S.load_tape(d)
        f = S.L2Features(cols)(d)
        # the flow layer's own session window starts 17:00 ET the evening before (research/flow.py _window_ns): the
        # sign carry starts there. (The 2023-11-24 tape file also holds the Thanksgiving session's prints before it.)
        k0 = int(np.searchsorted(tape.ts, midnight_ns(d) - 7 * 3600 * NS, "left"))
        tape = S.Tape(tape.root, tape.date, tape.contract, tape.ts[k0:], tape.px[k0:], tape.size[k0:])
        full = flow_minutes(tape.ts, tape.px, tape.size)
        lo, hi = int(tape.ts[0] // NS), int(tape.ts[-1] // NS)
        tu = f.cols["t_utc"]
        for i in np.flatnonzero((tu >= lo) & (tu <= hi)):
            row = tuple(float(f.cols[c][i]) for c in cols[:4])
            mine = full.get(int(tu[i]))
            if mine is None:
                assert all(v != v for v in row[:1]), (iso, int(tu[i]), row)          # no print -> NaN flow
            else:
                assert row == mine, (iso, int(tu[i]), row, mine)
                n_rows += 1
        t0 = midnight_ns(d)
        for hhmm in (2 * 3600 + 17 * 60, 9 * 3600 + 30 * 60, 9 * 3600 + 46 * 60, 12 * 3600 + 5 * 60, 15 * 3600):
            T = t0 + hhmm * NS
            k = int(np.searchsorted(tape.ts, T, "left"))
            part = flow_minutes(tape.ts[:k], tape.px[:k], tape.size[:k])
            want = {m: v for m, v in full.items() if m < T // NS}
            assert part == want, (iso, hhmm)
            n_trunc += len(part)
    print(f"\n[flow columns] {n_rows} minute rows equal to the tape's own minute; {n_trunc} minute values identical from a "
          f"tape truncated at the decision time")
    assert n_rows > 9000
