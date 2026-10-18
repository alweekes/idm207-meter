"""Carve the embedded LabVIEW resource file out of WinDMM.EXE and dump each
CPRF (compressed VI/menu) resource to its own file.

usage: python3 carve.py WinDMM.EXE out_dir
"""
import os, re, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rsrc

exe, out = sys.argv[1], sys.argv[2]
d = open(exe, 'rb').read()
base = re.search(rb'RSRC\r\n\x00\x03APPL', d).start()
info_ofs, info_len = struct.unpack_from('>II', d, base + 16)
app = d[base:base + info_ofs + info_len]
os.makedirs(out, exist_ok=True)
for typ, rid, name, p, ln in rsrc.parse(app)[1]:
    if typ == 'CPRF':
        open(os.path.join(out, name.replace('/', '_')), 'wb').write(app[p:p + ln])
        print(name, ln)
