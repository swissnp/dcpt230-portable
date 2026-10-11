"""Decode all pages of a portable PJL/PWG job using the system CUPS library."""
import ctypes
import ctypes.util
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile

lib = ctypes.CDLL(ctypes.util.find_library('cups'))
lib.cupsRasterOpen.argtypes = [ctypes.c_int, ctypes.c_int]
lib.cupsRasterOpen.restype = ctypes.c_void_p
lib.cupsRasterReadHeader2.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
lib.cupsRasterReadPixels.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint]
lib.cupsRasterClose.argtypes = [ctypes.c_void_p]
jobs = []
for job in Path(sys.argv[1]).read_bytes().split(b'\x1b%-12345X\x1b%-12345X'):
    if not job:
        continue
    pjl,raster = job.split(b'RaS2',1)
    with tempfile.TemporaryFile() as f:
        f.write(b'RaS2'+raster); f.seek(0)
        r = lib.cupsRasterOpen(f.fileno(),0)
        assert r
        pages = []
        try:
            while True:
                header = ctypes.create_string_buffer(1796)
                if not lib.cupsRasterReadHeader2(r,header):
                    break
                w,h = struct.unpack_from('=II',header.raw,372)
                bpl = struct.unpack_from('=I',header.raw,392)[0]
                row = ctypes.create_string_buffer(bpl)
                digest = hashlib.sha256()
                for _ in range(h):
                    assert lib.cupsRasterReadPixels(r,row,bpl)==bpl
                    digest.update(row.raw)
                pages.append(dict(width=w,height=h,sha256=digest.hexdigest()))
        finally:
            lib.cupsRasterClose(r)
        jobs.append(dict(pages=pages))
print(json.dumps(dict(jobs=jobs,page_count=sum(len(j['pages']) for j in jobs)),indent=2))
