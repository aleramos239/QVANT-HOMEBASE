import struct,sys,datetime as dt
def cfb_stream(path,name='Workbook'):
    d=open(path,'rb').read()
    ss=1<<struct.unpack_from('<H',d,30)[0]; mini=1<<struct.unpack_from('<H',d,32)[0]
    nfat=struct.unpack_from('<I',d,44)[0]; dir0=struct.unpack_from('<I',d,48)[0]
    cutoff=struct.unpack_from('<I',d,56)[0]; mf=struct.unpack_from('<I',d,60)[0]; nmf=struct.unpack_from('<I',d,64)[0]
    difat=list(struct.unpack_from('<109I',d,76))
    dif0=struct.unpack_from('<I',d,68)[0]; ndif=struct.unpack_from('<I',d,72)[0]
    sec=lambda i:d[512+i*ss:512+(i+1)*ss] if ss==512 else d[ss+i*ss:ss+(i+1)*ss]
    s=dif0
    for _ in range(ndif):
        x=struct.unpack('<%dI'%(ss//4),sec(s)); difat+=list(x[:-1]); s=x[-1]
    fat=[]
    for f in difat[:nfat]:
        fat+=list(struct.unpack('<%dI'%(ss//4),sec(f)))
    def chain(s):
        out=[]
        while s<0xFFFFFFFA: out.append(s); s=fat[s]
        return out
    dirb=b''.join(sec(i) for i in chain(dir0))
    ents=[]
    for i in range(len(dirb)//128):
        e=dirb[i*128:(i+1)*128]
        nl=struct.unpack_from('<H',e,64)[0]
        nm=e[:nl-2].decode('utf-16le') if nl>=2 else ''
        ents.append((nm,e[66],struct.unpack_from('<I',e,116)[0],struct.unpack_from('<I',e,120)[0]))
    for nm,ty,st,sz in ents:
        if nm==name:
            if sz<cutoff: raise Exception('mini stream')
            return b''.join(sec(i) for i in chain(st))[:sz]
def records(b):
    p=0
    while p+4<=len(b):
        t,l=struct.unpack_from('<HH',b,p); yield t,b[p+4:p+4+l]; p+=4+l
def sst(recs_iter):
    pass
def read(path):
    b=cfb_stream(path)
    recs=list(records(b))
    # SST with CONTINUE
    strings=[]
    i=0
    while i<len(recs):
        if recs[i][0]==0x00FC:
            data=bytearray(recs[i][1]); 
            # collect continues, remember boundaries
            bounds=[len(data)]
            j=i+1
            while j<len(recs) and recs[j][0]==0x003C:
                data+=recs[j][1]; bounds.append(len(data)); j+=1
            cnt=struct.unpack_from('<I',data,4)[0]; p=8
            for _ in range(cnt):
                nch=struct.unpack_from('<H',data,p)[0]; fl=data[p+2]; p+=3
                rt=0;ex=0
                if fl&8: rt=struct.unpack_from('<H',data,p)[0]; p+=2
                if fl&4: ex=struct.unpack_from('<I',data,p)[0]; p+=4
                u=fl&1; chars=[]; n=nch
                while n>0:
                    # boundary handling
                    nb=[x for x in bounds if x>p]
                    end=nb[0] if nb else len(data)
                    w=2 if u else 1
                    take=min(n,(end-p)//w)
                    seg=data[p:p+take*w]
                    chars.append(seg.decode('utf-16le') if u else seg.decode('latin1'))
                    p+=take*w; n-=take
                    if n>0 and p==end:
                        u=data[p]&1; p+=1
                p+=rt*4+ex
                strings.append(''.join(chars))
            i=j
        else: i+=1
    sheets=[];cur=-1;cells={}
    for t,r in recs:
        if t==0x0809 and len(r)>=4 and struct.unpack_from('<H',r,2)[0]==0x10: cur+=1
        if t==0x00FD: row,col,xf,idx=struct.unpack_from('<HHHI',r); cells[(cur,row,col)]=strings[idx]
        elif t==0x0203: row,col,xf=struct.unpack_from('<HHH',r); cells[(cur,row,col)]=struct.unpack_from('<d',r,6)[0]
        elif t==0x027E:
            row,col,xf,rk=struct.unpack_from('<HHHI',r)
            v=(rk>>2) if not rk&2 else struct.unpack('<d',struct.pack('<Q',(rk&0xFFFFFFFC)<<32))[0]
            if rk&2: v=(rk>>2)-(1<<30) if (rk>>2)&(1<<29) else (rk>>2)
            if rk&1: v/=100
            cells[(cur,row,col)]=v
        elif t==0x00BD:
            row,col=struct.unpack_from('<HH',r); n=(len(r)-6)//6
            for k in range(n):
                xf,rk=struct.unpack_from('<HI',r,4+6*k)
                v=(rk>>2)
                if rk&2:
                    if v&(1<<29): v-=(1<<30)
                else: v=struct.unpack('<d',struct.pack('<Q',(rk&0xFFFFFFFC)<<32))[0]
                if rk&1: v=v/100
                cells[(cur,row,col+k)]=v
        elif t==0x0085: 
            nl=r[6]; fl=r[7]; sheets.append(r[8:8+nl*(2 if fl&1 else 1)].decode('utf-16le' if fl&1 else 'latin1'))
    return sheets,cells
if __name__=='__main__':
    sheets,cells=read(sys.argv[1]); print(sheets)
    rows={}
    for (s,r,c),v in cells.items(): rows.setdefault((s,r),{})[c]=v
    for k in sorted(rows)[:int(sys.argv[2]) if len(sys.argv)>2 else 40]: print(k,dict(sorted(rows[k].items())))
