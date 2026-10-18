import sys,os,struct
src,dst=sys.argv[1],sys.argv[2]; os.makedirs(dst,exist_ok=True)
for f in os.listdir(src):
    d=open(os.path.join(src,f),'rb').read()
    n=struct.unpack('>I',d[:4])[0]; nc=(n+7)//8
    ctl=d[4:4+nc]; lit=d[4+nc:]; out=bytearray(); li=0
    for i in range(n):
        if ctl[i>>3]>>(i&7)&1: out.append(lit[li]); li+=1
        else: out.append(0)
    open(os.path.join(dst,f),'wb').write(out)
    print(f, n, li==len(lit))
