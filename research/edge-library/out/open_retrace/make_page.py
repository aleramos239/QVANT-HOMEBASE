import json
d=json.load(open("final.json")); cal=d["cal"]; rows=d["rows"]
idx=list(range(0,len(cal),5))+([len(cal)-1] if (len(cal)-1)%5 else [])
labels=[cal[i] for i in idx]
cur=[]
for c in rows:
    p=c["prop"]
    cur.append({"k":int(round(c["K"]*100)),"s":int(round(c["s"]*100)),"t":int(round(c["t"]*100)),"n":c["trades"],"net":c["net"],"avg":round(c["avg"]),"win":round(100*c["win"]),"pf":c["pf"],
        "dd":c["dd"],"sh":c["sharpe"],"wol":c["wol"],"mic":c["mic_med"],"eq":[int(round(c["eq"][i]/10.0))*10 for i in idx],
        "p":round(100*p["p"],1),"b0":round(100*p["base"],1),"edge":round(100*p["edge"],1),"t_":round(p["t"],2),"beats":p["beats"],"ahead":p["ahead"],
        "pay":round(100*p["pay"]),"fb":round(100*p["fbust"]),"ech":round(p["ech"]),"ev":round(p["evals"],1),"w":round(100*p["degp"],1)})
data=json.dumps({"labels":labels,"c":cur},separators=(",",":"))
tpl=open("page_tpl.html").read().replace("__DATA__",data)
open("judas-risk500.html","w").write(tpl)
open("test2.html","w").write('<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>body{margin:0}</style>'+tpl)
print(len(tpl)//1024,"KB")
