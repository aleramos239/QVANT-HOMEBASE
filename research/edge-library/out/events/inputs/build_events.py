import json,re,csv,datetime as dt,collections,sys
sys.path.insert(0,'.')
LO,HI=dt.date(2021,9,1),dt.date(2026,9,30)
rows=[]   # (date, time, type, subtype, source)
def add(d,tm,ty,sub,src):
    if isinstance(d,str): d=dt.date.fromisoformat(d)
    if LO<=d<=HI:
        assert d.weekday()<5,(d,ty)
        rows.append((str(d),tm,ty,sub,src))
# ---- BLS
A=json.load(open('bls_A.json'))
TY={'empsit':'NFP','cpi':'CPI','ppi':'PPI','jolts':'JOLTS'}
for s,ty in TY.items():
    for d,(tm,desc) in A[s].items():
        t24=dt.datetime.strptime(tm,'%I:%M %p').strftime('%H:%M')
        add(d,t24,ty,'',f'bls.gov/schedule/{d[:4]}/home.htm + bls.gov/bls/news-release/{s}.htm')
# ---- BEA
B=json.load(open('bea_rows.json'))
seen={}
for k in ('pio','gdp','gdp2'):
    for u,t,d in B[k]: seen[u]=(re.sub(r'\s+',' ',t).strip(),d)
for u,(t,d) in seen.items():
    day=dt.date.fromisoformat(d[:10]); tm=d[11:16]
    if tm=='08:31': tm='08:30'
    if not (LO<=day<=HI): continue
    src='bea.gov'+u
    if t.startswith('Personal Income and Outlays'):
        add(day,tm,'PCE','data_update' if 'Data Update' in t else '',src)
    elif re.search(r'(Gross Domestic Product|GDP)',t) and re.search(r'\((Advance|Initial|Second|Third|Updated) Estimate\)',t) and not re.search(r'by State and|for (American|Guam|Puerto|the)',t):
        m=re.search(r'\((Advance|Initial|Second|Third|Updated) Estimate\)',t).group(1)
        sub={'Advance':'advance','Initial':'advance','Second':'second','Third':'third','Updated':'third'}[m]
        add(day,tm,'GDP',sub,src)
# ---- Census retail
from xlsread import read
sheets,cells=read('marts.xls')
rw={}
for (s,r,c),v in cells.items(): rw.setdefault(r,{})[c]=v
retail={}
for r in rw:
    y=rw[r].get(0)
    if isinstance(y,float) and 2021<=y<=2025:
        for c in range(1,13):
            v=rw[r].get(c)
            if isinstance(v,float): retail[dt.date(int(y),c,int(v))]='https://www.census.gov/retail/marts/www/MARTSreleasedates.xls'
# 2025 Oct N/A; Nov 25, Dec 16 are in xls as strings '25**','16**' -> take from release_schedule page
for d in ['2025-11-25','2025-12-16','2026-01-14','2026-02-10','2026-03-06','2026-04-01','2026-04-21','2026-05-14','2026-06-17','2026-07-16','2026-08-14','2026-09-16']:
    retail[dt.date.fromisoformat(d)]='https://www.census.gov/retail/release_schedule.html'
for d,src in retail.items(): add(d,'08:30','RETAIL','',src.replace('https://www.',''))
# ---- DOL claims
cl=json.load(open('claims_thu.json'))
wed={'2021-11-10','2021-11-24','2022-11-23','2023-11-22','2024-07-03','2024-11-27','2025-01-08','2025-06-18','2025-11-26','2025-12-24','2025-12-31'}
for d,c in cl.items():
    if c in('200','206'): add(d,'08:30','CLAIMS','',f'oui.doleta.gov/press/{d[:4]}/{d[5:7]}{d[8:10]}{d[2:4]}.pdf')
for d in wed:
    add(d,'08:30','CLAIMS','moved',f'oui.doleta.gov/press/{d[:4]}/{d[5:7]}{d[8:10]}{d[2:4]}.pdf')
# ---- ISM
P=json.load(open('ism_pr.json'))
for ds,tm,ti in P:
    day=dt.datetime.strptime(ds,'%b %d, %Y').date()
    if re.match(r'Manufacturing PMI',ti): add(day,tm,'ISM_MFG','','prnewswire.com/news/institute-for-supply-management/ (ISM release stamp)')
    elif re.match(r'(Services|Non-Manufacturing) PMI',ti): add(day,tm,'ISM_SVC','','prnewswire.com/news/institute-for-supply-management/ (ISM release stamp)')
# ---- UMich
for l in open('umich_hist.txt'):
    m=re.match(r'(\w{3}) (\d{4}) (\d+)/(\d+)/(\d{4}) ',l)
    if m: add(dt.date(int(m.group(5)),int(m.group(3)),int(m.group(4))),'10:00','UMICH','','data.sca.isr.umich.edu/fetchdoc.php?docid=75443')
# ---- FOMC
for d,_ in json.load(open('fomc.json')): add(d,'14:00','FOMC','','federalreserve.gov/monetarypolicy/fomccalendars.htm')
rows=sorted(set(rows))
json.dump(rows,open('events_rows.json','w'))
c=collections.Counter()
for r in rows: c[(r[2],r[0][:4])]+=1
types=['NFP','CPI','PPI','RETAIL','GDP','PCE','CLAIMS','ISM_MFG','ISM_SVC','JOLTS','UMICH','FOMC']
for t in types: print(t,[c[(t,str(y))] for y in range(2021,2027)],sum(c[(t,str(y))] for y in range(2021,2027)))
