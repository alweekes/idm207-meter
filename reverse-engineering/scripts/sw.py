import sys,struct,capstone
d=open(sys.argv[1],'rb').read()
tab=int(sys.argv[2],16); n=int(sys.argv[3],16)
md=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_32)
tg=[]
for i in range(n):
    e=tab+4*i; t=(e+struct.unpack_from('<i',d,e)[0])&0xffffffff; tg.append(t)
print([hex(t) for t in tg])
for i,t in enumerate(tg):
    if t in tg[:i]: print('case',i,'-> same as',tg.index(t)); continue
    out=[]
    for ins in md.disasm(d[t:t+400],t):
        s=f"{ins.mnemonic} {ins.op_str}"
        if ins.mnemonic=='jmp': out.append(s); break
        out.append(s)
    print('case',i,hex(t),' | '.join(out))
