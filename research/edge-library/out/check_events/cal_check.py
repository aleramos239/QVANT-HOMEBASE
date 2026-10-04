"""Checker stage 3: calendar checks with own code (no market data)."""
import csv, datetime as dt, collections, random, json
from pathlib import Path
W = Path(__file__).resolve().parents[2]
R = list(csv.DictReader(open(W/'engine/cache/events.csv')))
print('rows', len(R), R[0]['date'], R[-1]['date'])
# weekday / duplicates
wk = [r for r in R if dt.date.fromisoformat(r['date']).weekday() >= 5]
print('weekend rows', len(wk))
dup = [k for k, v in collections.Counter((r['date'], r['type']) for r in R).items() if v > 1]
print('dup (date,type)', dup)
c = collections.Counter((r['type'], r['date'][:4]) for r in R)
types = sorted({r['type'] for r in R})
for t in types:
    print(f"{t:8s}", [c[(t, str(y))] for y in range(2021, 2027)], sorted({r['time_et'] for r in R if r['type'] == t}))
# times per type
odd = [(r['date'], r['type'], r['time_et']) for r in R if (r['type'] in ('NFP','CPI','PPI','RETAIL','GDP','PCE','CLAIMS') and r['time_et'] != '08:30') or (r['type'] in ('ISM_MFG','ISM_SVC','JOLTS','UMICH') and r['time_et'] != '10:00') or (r['type']=='FOMC' and r['time_et']!='14:00')]
print('odd times', odd)
# weekday rules
claims = [r for r in R if r['type'] == 'CLAIMS']
print('claims not Thursday', [(r['date'], r['subtype']) for r in claims if dt.date.fromisoformat(r['date']).weekday() != 3])
# claims: every week has exactly one
wks = collections.Counter(dt.date.fromisoformat(r['date']).isocalendar()[:2] for r in claims if r['date'] < '2025-01-01')
print('claims weeks with !=1 (to 2024)', [k for k, v in wks.items() if v != 1])
d0, d1 = dt.date(2021, 9, 1), dt.date(2024, 12, 31)
allw = set()
d = d0
while d <= d1:
    allw.add(d.isocalendar()[:2]); d += dt.timedelta(days=1)
print('weeks without claims (to 2024)', sorted(allw - set(wks)))
print('NFP not Friday', [(r['date']) for r in R if r['type'] == 'NFP' and dt.date.fromisoformat(r['date']).weekday() != 4])
print('UMICH not Friday', [(r['date']) for r in R if r['type'] == 'UMICH' and dt.date.fromisoformat(r['date']).weekday() != 4])
print('FOMC not Wed', [(r['date']) for r in R if r['type'] == 'FOMC' and dt.date.fromisoformat(r['date']).weekday() != 2])
# monthly: one per month
for t in ('NFP','CPI','PPI','RETAIL','GDP','PCE','ISM_MFG','ISM_SVC','JOLTS','UMICH'):
    m = collections.Counter(r['date'][:7] for r in R if r['type'] == t and r['date'] < '2025-01-01')
    months = [f"{y}-{mm:02d}" for y in range(2021, 2025) for mm in range(1, 13) if (y, mm) >= (2021, 9)]
    bad = [(k, m.get(k, 0)) for k in months if m.get(k, 0) != 1]
    print(t, 'months !=1 (to 2024):', bad)
# old file
old = list(csv.DictReader(open(W.parent/'prop-portfolio/2026-09-29/news_days.csv')))
print('old cols', old[0].keys(), len(old))
new = {t: {r['date'] for r in R if r['type'] == t} for t in ('NFP', 'CPI', 'FOMC')}
oldd = {t: set() for t in new}
for r in old:
    for t in r['tags'].replace(';', ',').replace('|', ',').replace('+', ',').split(','):
        t = t.strip()
        if t in oldd: oldd[t].add(r['date'])
print('old tag kinds', collections.Counter(r['tags'] for r in old).most_common(8))
for lo, hi, lab in (('2021-09-01', '2024-12-31', 'to 2024'), ('2025-01-01', '2026-12-31', '2025+')):
    for t in new:
        a = {d for d in new[t] if lo <= d <= hi}; b = {d for d in oldd[t] if lo <= d <= hi}
        print(lab, t, 'new', len(a), 'old', len(b), 'only new', sorted(a - b), 'only old', sorted(b - a))
random.seed(20261004)
pool = [r for r in R if '2021-09-22' <= r['date'] <= '2024-12-31']
smp = sorted(random.sample(pool, 40), key=lambda r: (r['type'], r['date']))
json.dump(smp, open(W/'out/check_events/cal_sample40.json', 'w'), indent=0)
for r in smp: print(r['date'], dt.date.fromisoformat(r['date']).strftime('%a'), r['time_et'], r['type'], r['subtype'], '|', r['source'][:70])
