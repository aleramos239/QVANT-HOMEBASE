"""CHECKER stage 3: the 2024 judgement of the 4 BUILD passers, own code (stores already read by the analyst), + seal scans."""
import csv, json, sys, datetime as dt, glob, re
from pathlib import Path
import numpy as np
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(OUT))
import chk_build as B
W = B.W
PASS = [('E1-A-GC', 'straddle_tight_0830', 'GC', 'pre', 'A', 'runs_admit_r1'), ('E1-B-NQ', 'straddle_tight_0830', 'NQ', 'pre', 'B', 'runs_admit_r1'),
        ('E1-B-GC', 'straddle_tight_0830', 'GC', 'pre', 'B', 'runs_admit_r1'), ('E3-C-GC', 'straddle_tight_1000', 'GC', 'nyam', 'C', 'runs_events')]
bu = {r['uid']: r for r in json.load(open(OUT / 'chk_build.json'))}
reads = []
for uid, fam, root, sess, g, rd in PASS:
    cm = bu[uid]['central']
    key = f'{fam}-{root}-tf30-{sess}-pick'
    meta, z = B.load(key, rd)
    assert meta['period'] == 'pick' and z['date'].min() >= B.P0 and z['date'].max() <= B.P1
    gd = np.array(sorted(B.G[g]))
    keep, n_all, n_dead, n_dup = B.heat(meta, z, sess, gd)
    net = np.array([r['net'] for r in keep]); share = float((net > 0).mean()); med = float(np.median(net))
    i = next(k for k, c in enumerate(meta['cells']) if c['id'] == cm)
    x = B.cellx(meta, z, i); ms = x['sess'] == B.SESS[sess]
    ine = np.isin(x['date'], gd)
    clock = np.array(sorted(B.G['A'] if g in ('A', 'B') else B.G['C']))
    non = ~np.isin(x['date'], clock)
    ne, nn = x['net'][ms & ine], x['net'][ms & non]
    ms_, zs = B.load(key + '-shift', rd)
    ids = {c['id']: k for k, c in enumerate(ms_['cells'])}
    sh = []
    for sd in (1, 2):
        xs = B.cellx(ms_, zs, ids[f's{sd}_{cm}'])
        sh.append(float(xs['net'][np.isin(xs['date'], gd)].sum()))
    rank = sorted(net, reverse=True).index(float(ne.sum())) + 1 if float(ne.sum()) in net else None
    print(f"{uid} 2024 table: {len(keep)} cells, share>0 {share:.4f}, median {med:.2f} -> {'PASS' if share >= 0.6 and med > 0 else 'fail'} | central {cm}: {len(ne)} trades net {ne.sum():.2f} t {B.tstat(ne):.2f} rank {rank} | "
          f"non-event {len(nn)} trades {nn.sum():.2f} (lift/trade {ne.mean() - nn.mean():.2f}) | random-minute control {np.mean(sh):.2f} {sh} | 2024 event days {bu[uid]['ev24']} | BUILD+2024 trades {bu[uid]['trades'] + len(ne)}")
    reads.append((uid, fam, root, cm, g, '2024', f'whole menu ({len(keep)} cells) + random-minute control, day filter {g} (store {rd}/{key})', len(ne), round(float(ne.sum()), 2)))
with (OUT / 'checker_pick_reads.csv').open('a', newline='') as fh:
    csv.writer(fh).writerows(reads)
# ---- seals: every store / trade file written by stage 3 holds no date >= 2025-01-01
E0 = dt.date(2025, 1, 1).toordinal()
for d in sorted((W / 'runs_events').iterdir()):
    meta = json.loads((d / 'run.json').read_text()); z = np.load(d / 'cells.npz')
    print('store', d.name, 'period', meta.get('period'), 'cells', len(meta['cells']), 'trades', len(z['date']), 'dates', dt.date.fromordinal(int(z['date'].min())), '..', dt.date.fromordinal(int(z['date'].max())), 'EXAM!' if z['date'].max() >= E0 else 'ok')
mx = ''
for p in glob.glob(str(W / 'out/events/member_runs/*.json')) + glob.glob(str(W / 'members/straddle_tight_*_ev*/trades_*.json')):
    j = json.loads(Path(p).read_text()); tr = j['trades'] if isinstance(j, dict) else j
    mx = max(mx, max(t['date'] for t in tr))
print('latest trade date in stage-3 member files:', mx)
for p in sorted(glob.glob(str(W / 'out/events/*.py')) + glob.glob(str(W / 'out/events/inputs/*.py'))):
    s = Path(p).read_text()
    hits = [m for m in re.findall(r'allow_exam\s*=\s*True|allow_holdout\s*=\s*True|2025|2026|exam', s)]
    print(Path(p).name, 'hits:', sorted(set(hits)))
