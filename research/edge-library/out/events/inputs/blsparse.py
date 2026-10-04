import re,html,json,datetime as dt
out=[]
for y in range(2021,2027):
    t=open(f'wb/sched{y}.html',errors='ignore').read()
    for m in re.finditer(r'<tr class="release-list-(?:even|odd)-row">\s*<td class="date-cell"><p>([^<]+)</p></td>\s*<td class="time-cell"><p>([^<]*)</p></td>\s*<td class="desc-cell"><p>(.*?)</p></td>\s*</tr>',t,flags=re.S):
        d=dt.datetime.strptime(m.group(1).strip(),'%A, %B %d, %Y').date()
        desc=html.unescape(re.sub(r'<[^>]+>','',m.group(3)))
        name=html.unescape(re.sub(r'<[^>]+>','',re.search(r'<strong>(.*?)</strong>',m.group(3),flags=re.S).group(1))) if '<strong>' in m.group(3) else desc
        out.append((str(d),m.group(2).strip(),name.strip(),desc.strip(),y))
json.dump(out,open('bls_sched.json','w'))
import collections
c=collections.Counter((o[4],o[2]) for o in out if o[2] in('Employment Situation','Consumer Price Index','Producer Price Index','Job Openings and Labor Turnover Survey'))
for k in sorted(c): print(k,c[k])
