"""Checker stage 3: own recompute of the 15 BUILD units from the stores (no analyst / library judging functions)."""
import csv, json, math, sys, datetime as dt, hashlib
from pathlib import Path
import numpy as np
W = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
EV = [r for r in csv.DictReader(open(W / 'engine/cache/events.csv')) if r['date'] < '2025-01-01']
o = lambda d: dt.date.fromisoformat(d).toordinal()
T1 = {'NFP', 'CPI', 'PPI', 'RETAIL', 'GDP', 'PCE'}
T10 = {'ISM_MFG', 'ISM_SVC', 'JOLTS', 'UMICH'}
G = {'A': {o(r['date']) for r in EV if r['time_et'] == '08:30'},
     'B': {o(r['date']) for r in EV if r['time_et'] == '08:30' and r['type'] in T1},
     'C': {o(r['date']) for r in EV if r['time_et'] == '10:00'},                      # analyst's reading (incl. 10:00 PCE)
     'Cstrict': {o(r['date']) for r in EV if r['time_et'] == '10:00' and r['type'] in T10}}
SESS = {'eve': 0, 'asia': 1, 'london': 2, 'pre': 3, 'nyam': 4, 'mid': 5, 'pm': 6}
BAR = {'NQ': 2.56, 'ES': 2.0010262339325084, 'GC': 1.63}
B0, B1, P0, P1 = o('2021-09-22'), o('2023-12-31'), o('2024-01-01'), o('2024-12-31')

def load(key, runs='runs'):
    d = W / runs / key
    meta = json.loads((d / 'run.json').read_text())
    z = np.load(d / 'cells.npz')
    return meta, {k: z[k] for k in z.files}

def cellx(meta, z, i):
    a, b = int(z['off'][i]), int(z['off'][i + 1])
    return {k: z[k][a:b] for k in z if k != 'off'}

def tstat(x):
    x = np.asarray(x, float); n = len(x)
    if n < 2: return None
    sd = x.std(ddof=1)
    return float(x.mean() / (sd / math.sqrt(n))) if sd > 0 else None

def sig(x, m):
    h = hashlib.sha1()
    for k in ('entry_ms', 'dur_s', 'side'):
        h.update(np.ascontiguousarray(x[k][m]).astype(np.int64).tobytes())
    h.update(np.round(x['net'][m] * 100).astype(np.int64).tobytes())
    return h.hexdigest()

def heat(meta, z, sess, days):
    """rows of the judged heat map on `days` (None = all): dead variants (no trade in the session in ANY exit cell, all days) out,
    identical trade lists counted once (first in (vi, xi) order)."""
    rows = []
    for i, c in enumerate(meta['cells']):
        if c.get('info'): continue
        x = cellx(meta, z, i)
        ms = x['sess'] == SESS[sess]
        m = ms if days is None else ms & np.isin(x['date'], days)
        rows.append({'id': c['id'], 'vi': c['vi'], 'xi': c['xi'], 'n_sess': int(ms.sum()), 'n': int(m.sum()), 'net': float(x['net'][m].sum()),
                     'sig': sig(x, m) if m.any() else 'empty', 'i': i})
    alive = {r['vi'] for r in rows if r['n_sess'] > 0}
    live = sorted([r for r in rows if r['vi'] in alive], key=lambda r: (r['vi'], r['xi']))
    seen, keep = set(), []
    for r in live:
        if r['sig'] in seen: continue
        seen.add(r['sig']); keep.append(r)
    return keep, len(rows), len(rows) - len(live), len(live) - len(keep)

def central(keep):
    net = np.array([r['net'] for r in keep])
    med = float(np.median(net))
    pos = [r for r in keep if r['net'] > 0]
    if not pos: return None, med, 0.0
    c = min(pos, key=lambda r: (round(abs(r['net'] - med), 6), r['vi'], r['xi']))
    return c, med, len(pos) / len(keep)

def unit(code, fam, sess, g, root, draws=4000, seed=7):
    meta, z = load(f'{fam}-{root}-tf30')
    assert meta.get('period') == 'build', meta.get('period')
    assert z['date'].min() >= B0 and z['date'].max() <= B1, (z['date'].min(), z['date'].max())
    gd = np.array(sorted(G[g]))
    keep, n_all, n_dead, n_dup = heat(meta, z, sess, gd)
    c, med, share = central(keep)
    keep_all, *_ = heat(meta, z, sess, None)
    c_all, med_all, share_all = central(keep_all)
    row = {'uid': f'{code}-{g}-{root}', 'cells': len(keep), 'cells_all': n_all, 'dead': n_dead, 'dup': n_dup, 'share_pos': round(share, 4), 'median': round(med, 2),
           'central': c['id'] if c else None, 'alldays_share': round(share_all, 4), 'alldays_central': c_all['id'] if c_all else None}
    if c is None:
        row.update(passed=False); return row
    x = cellx(meta, z, c['i'])
    ms = x['sess'] == SESS[sess]
    ine = np.isin(x['date'], gd)
    clock = np.array(sorted(G['A'] if g in ('A', 'B') else G['C' if g == 'C' else 'Cstrict']))
    non = ~np.isin(x['date'], clock)
    ne, nn = x['net'][ms & ine], x['net'][ms & non]
    t = tstat(ne) or 0.0
    lift = ne.mean() - (nn.mean() if len(nn) else 0.0)
    # (e) random same-size subsets of the days the central variant traded (session trades)
    d = x['date'][ms]; nets = x['net'][ms]
    days, inv = np.unique(d, return_inverse=True)
    daily = np.zeros(len(days)); np.add.at(daily, inv, nets)
    k = int(np.isin(days, gd).sum()); obs = float(daily[np.isin(days, gd)].sum())
    rng = np.random.default_rng(seed)
    sims = np.array([daily[rng.choice(len(days), k, replace=False)].sum() for _ in range(draws)])
    pct = float((obs > sims).mean())
    # 2024 event days of the calendar (count only; sessions = weekdays that are event days) -- count taken from the calendar file
    ev24 = sum(1 for dd in G[g] if P0 <= dd <= P1)
    # random-minute control (shift store), same days
    try:
        ms_, zs = load(f'{fam}-{root}-tf30-shift')
        ids = {cc['id']: i for i, cc in enumerate(ms_['cells'])}
        sh = []
        for sd in (1, 2):
            xs = cellx(ms_, zs, ids[f's{sd}_{c["id"]}'])
            sh.append(float(xs['net'][np.isin(xs['date'], gd)].sum()))
        shift = float(np.mean(sh))
    except Exception as e:
        shift = None
    a = len(ne) + ev24 >= 100
    b = med > 0 and share >= 0.60 - 1e-12
    cc_ = lift > 0
    dd_ = t >= BAR[root]
    e = pct >= 1 - 0.05 / 15
    row.update(trades=len(ne), net=round(float(ne.sum()), 2), t=round(t, 3), bar=BAR[root], non_trades=len(nn), non_net=round(float(nn.sum()), 2),
               mean_ev=round(float(ne.mean()), 2), mean_non=round(float(nn.mean()), 2) if len(nn) else None, lift=round(float(lift), 2),
               pct=round(100 * pct, 2), days_in=k, days_all=len(days), ev24=ev24, shift_mean=None if shift is None else round(shift, 2),
               a=a, b=b, c=cc_, d=dd_, e=e, passed=bool(a and b and cc_ and dd_ and e))
    return row

UNITS = [('E1', 'straddle_tight_0830', 'pre', ('A', 'B')), ('E2', 'straddle_t_0830', 'pre', ('A', 'B')), ('E3', 'straddle_tight_1000', 'nyam', ('C', 'Cstrict'))]
if __name__ == '__main__':
    rows = []
    for code, fam, sess, gs in UNITS:
        for g in gs:
            for root in ('NQ', 'ES', 'GC'):
                rows.append(unit(code, fam, sess, g, root))
    json.dump(rows, open(OUT / 'chk_build.json', 'w'), indent=1, default=lambda v: bool(v) if isinstance(v, np.bool_) else float(v))
    an = {r['uid']: r for r in csv.DictReader(open(W / 'out/events/build_units.csv'))}
    for r in rows:
        a_ = an.get(r['uid'])
        print(f"{r['uid']:14s} cells {r['cells']:3d} (dead {r['dead']} dup {r['dup']}) pos {r['share_pos']:.4f} med {r['median']:9.2f} central {str(r['central']):18s} n {r.get('trades')} net {r.get('net')} t {r.get('t')} "
              f"lift {r.get('lift')} pct {r.get('pct')} shift {r.get('shift_mean')} a{int(r.get('a',0))}b{int(r.get('b',0))}c{int(r.get('c',0))}d{int(r.get('d',0))}e{int(r.get('e',0))} {'PASS' if r['passed'] else 'fail'}")
        if a_:
            diff = []
            for k1, k2, tol in (('share_pos', 'share_pos', 1e-4), ('median', 'median_net', 0.011), ('trades', 'trades', 0), ('net', 'net', 0.011), ('t', 't', 2e-3), ('lift', 'lift_mean', 0.011)):
                if r.get(k1) is None: continue
                if abs(float(r[k1]) - float(a_[k2])) > tol: diff.append((k1, r[k1], a_[k2]))
            if r['central'] != a_['central']: diff.append(('central', r['central'], a_['central']))
            if str(r['passed']) != a_['pass']: diff.append(('pass', r['passed'], a_['pass']))
            for k in 'abcde':
                if str(bool(r.get(k))) != a_[k]: diff.append((k, r.get(k), a_[k]))
            print('    analyst: e_p', a_['e_p'], 'days_in', a_['days_in'], a_['days_all'], 'ev days', a_['event_days_build'], a_['event_days_2024'], '| DIFF:' if diff else '| same', diff or '')
