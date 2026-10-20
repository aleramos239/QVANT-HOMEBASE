"""3:1 BLOCK WALK-FORWARD of the owner's FVG idea (fvg_odir, NQ 15m), the owner's order of 2026-10-19 (CLAUDE.md: OOS = the 3:1 block
walk-forward on every route). The versions the walk picks from are FIXED HERE before any walk-forward result:
    entry  first | newest FVG     stop  middle candle | 1x / 2x / 3x the 1-minute ATR14     target  0.5 / 0.75 / 1 / 1.25 R
    limit  1 trade a day | none (20; newest only)                                            -> 16 + 16 + 16 = 48 versions
Every version is run on every session day 2021-09-22 .. the last whole month, one contract after costs (the engine's own), strict limits.
The walk is the pipeline's own (blueprint/pipe_wf.py): pick on 3 whole months, trade the 4th, next block (pipeline.json walkforward);
the pick = the MIDDLE version by average trade of those that make money, have 15+ trades and hold P3.15 in the window; none = stand aside.
Judged by P6.1 (net > 0), P6.3 (P3.15 on the stitched trades), P6.4 (200+ trades). P6.2 (beats random) is NOT run: this rule's stop has
no random pool yet -- said in the output.

    python taught/wf_fvg_odir.py run      the engine passes (stores in ~/.homebase/taught/wf_fvg_odir/)
    python taught/wf_fvg_odir.py walk     the walk off the stores
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(HERE), str(HERE / 'engine')]

import datetime as dt
import json

import numpy as np

OUT = Path.home() / '.homebase/taught/wf_fvg_odir'
BASE = Path.home() / '.homebase/taught/owner_fvg_odir_15_nl_new/runs/owner_fvg_odir_15_nl_new-NQ-tf15/run.json'
END = '2026-09-30'                                   # the last whole month


def versions() -> list:
    out = []
    for pick, cap in (('first', 1), ('newest', 1), ('newest', 20)):
        for atr in (0.0, 1.0, 2.0, 3.0):
            for r in (0.5, 0.75, 1.0, 1.25):
                vid = f"{pick}{'' if cap == 1 else '_nolim'}_{'mid' if not atr else f'atr{atr:g}'}_r{r:g}"
                out.append({'id': vid, 'pick': pick, 'max_tr': cap, 'atr1': atr, 'tgt_r': r})
    return out


def run():
    import l2sim as S
    import library as LB
    from families import blocks
    base = json.load(open(BASE))['cells'][1]['inputs']
    vs = versions()
    specs = [(blocks.WRAPPED['fvg_odir'], {**base, 'pick': v['pick'], 'max_tr': v['max_tr'], 'atr1': v['atr1'], 'tgt_r': v['tgt_r']}) for v in vs]
    OUT.mkdir(parents=True, exist_ok=True)
    test_days = [d.isoformat() for d in S.sessions(S.BP_TEST_START, END, 'NQ', allow_holdout=S.ALLOW_BT)]
    parts = {'build': lambda: S.run_many(specs, root='NQ', workers=4, period=S.ALLOW_BP, strict_limit=True),
             'test': lambda: S.run_many(specs, test_days[0], test_days[-1], root='NQ', workers=4, allow_holdout=S.ALLOW_BT, days=test_days,
                                        strict_limit=True)}
    for part, go in parts.items():
        f = OUT / f'{part}.npz'
        if f.exists():
            print(part, 'on disk', flush=True)
            continue
        res = go()
        arrs = {}
        for v, r in zip(vs, res):
            assert r['skipped_by_error'] == 0, (v['id'], r['no_trade'][:3])
            for k, a in LB.pack(r['trades']).items():
                arrs[f"{v['id']}|{k}"] = a
        cal = sorted({d for r in res for d in r.get('meta', {}).get('calendar', [])}) or None
        np.savez(f, **arrs)
        (OUT / f'{part}.json').write_text(json.dumps({'versions': vs, 'sessions': res[0]['sessions'], 'used': res[0]['used'], 'calendar': cal}))
        print(part, 'done', res[0]['sessions'], 'sessions', flush=True)


def walk():
    import l2sim as S
    import library as LB
    from blueprint import pipe_rules as PR
    from blueprint import pipe_wf as WF
    vs = versions()
    b, t = np.load(OUT / 'build.npz'), np.load(OUT / 'test.npz')
    boxes = {}
    for v in vs:
        x = {k: np.concatenate([b[f"{v['id']}|{k}"], t[f"{v['id']}|{k}"]]) for k in LB.FIELDS}
        o = np.argsort(x['entry_ms'], kind='stable')
        x = {k: a[o] for k, a in x.items()}
        x['month'] = WF._month(x['date'])
        boxes[v['id']] = x
    rows = [{'id': v['id'], 'net': float(boxes[v['id']]['net'].sum()), 'vi': i, 'xi': 0} for i, v in enumerate(vs)]
    cal = [d.isoformat() for d in S.sessions(S.BP_BUILD[0], S.BP_BUILD[1], 'NQ', allow_holdout=S.ALLOW_BP)] + \
          [d.isoformat() for d in S.sessions(S.BP_TEST_START, END, 'NQ', allow_holdout=S.ALLOW_BT)]
    wf = PR.need('walkforward')
    ms = WF.months(cal)
    got = WF.walk(boxes, rows, ms, wf['select_months'], wf['window_trades'], '2026-10-19', wf['step_months'])
    x = WF.stitch(boxes, got['picks'])
    x.update({k: np.concatenate([boxes[p['cell']][k][boxes[p['cell']]['month'] == p['month']] for p in got['picks'] if p['cell']])
              for k in ('side', 'sess', 'reason', 'risk')})
    out = WF.rows(x, None, PR.need('variant', 'region_trades'))
    tested = {p['month'] for p in got['picks']}
    tcal = np.array([dt.date.fromisoformat(d).toordinal() for d in cal if d[:7] in tested])
    res = {'picks': got['picks'], 'next': got['next'], 'rows': out, 'calendar_days': len(tcal)}
    (OUT / 'walk.json').write_text(json.dumps(res, indent=1, default=str))
    np.savez(OUT / 'stitched.npz', **x, tcal=tcal)
    for p in got['picks']:
        m = boxes[p['cell']]['month'] == p['month'] if p['cell'] else None
        print(p['month'], 'pick', p['cell'] or 'STAND ASIDE', '' if m is None else f"trades {int(m.sum())} net ${boxes[p['cell']]['net'][m].sum():,.0f}")
    print('next', got['next'])
    for r in out:
        print(r['line'], r['passed'], r['text'])
    print('P6.2 not run: no random pool for this rule\'s own stop yet')


if __name__ == '__main__':
    {'run': run, 'walk': walk}[sys.argv[1]]()
