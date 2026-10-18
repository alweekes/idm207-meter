import struct
def parse(d, base=0):
    magic,ver,typ,cre,io,il,do,dl=struct.unpack_from('>6sH4s4sIIII',d,base)
    info=base+io
    lo=struct.unpack_from('>I',d,info+0x2c)[0]  # list offset? 0x34
    nameofs=struct.unpack_from('>I',d,info+0x30)[0]
    tl=info+0x34
    n=struct.unpack_from('>I',d,tl)[0]+1
    res=[]
    for i in range(n):
        t,c,o=struct.unpack_from('>4sII',d,tl+4+12*i)
        for j in range(c+1):
            rid,nofs,x,dofs,y=struct.unpack_from('>iIIII',d,tl+o+20*j)
            name=None
            if nofs!=0xffffffff:
                p=info+nameofs+nofs; name=d[p+1:p+1+d[p]].decode('latin1')
            p=base+do+dofs
            ln=struct.unpack_from('>I',d,p)[0]
            res.append((t.decode('latin1'),rid,name,p+4,ln))
    return typ.decode(),res
if __name__=='__main__':
    import sys
    d=open(sys.argv[1],'rb').read()
    typ,res=parse(d,int(sys.argv[2],16) if len(sys.argv)>2 else 0)
    print(typ)
    for r in res: print(r[0],r[1],repr(r[2]),hex(r[3]),r[4])
