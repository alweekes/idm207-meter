import struct,sys
d=open(sys.argv[1],'rb').read()
def td(p):
    sz,fl,ty=struct.unpack_from('>HBB',d,p)
    return sz,fl,ty
sz,fl,ty=td(0); n=struct.unpack_from('>H',d,4)[0]
print('top',hex(sz),hex(fl),hex(ty),n)
p=6
for i in range(n):
    sz,fl,ty=td(p)
    extra=d[p+4:p+min(sz,16)].hex()
    lbl=''
    if fl&0x40:
        # label at end: pascal string; find by scanning backwards
        body=d[p:p+sz]
        for k in range(sz-1,3,-1):
            L=body[k]
            if k+1+L==sz or k+1+L==sz-1:
                s=body[k+1:k+1+L]
                if all(32<=c<127 for c in s) and L>0: lbl=s.decode(); break
    print(i,hex(p),sz,hex(fl),hex(ty),extra,lbl)
    p+=sz
