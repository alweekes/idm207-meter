import sys,capstone
d=open(sys.argv[1],'rb').read()
md=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_32)
for i in md.disasm(d[int(sys.argv[2],0) if len(sys.argv)>2 else 0:],0):
    print(f"{i.address:06x}: {i.mnemonic} {i.op_str}")
