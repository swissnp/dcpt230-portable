#!/usr/bin/env python3
"""Build an architecture-independent Debian package without dpkg-deb."""
import gzip
import io
from pathlib import Path
import tarfile

ROOT = Path(__file__).resolve().parents[1]

def archive(files):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode='w', format=tarfile.USTAR_FORMAT) as tar:
        directories=set()
        for name,_,_ in files:
            directories.update(str(p) for p in Path(name).parents if str(p)!='.')
        for name in sorted(directories,key=lambda n:(n.count('/'),n)):
            info=tarfile.TarInfo(name+'/');info.type=tarfile.DIRTYPE
            info.mode=0o755;info.uid=info.gid=info.mtime=0
            info.uname=info.gname='root';tar.addfile(info)
        for name, data, mode in files:
            info = tarfile.TarInfo(name)
            info.size, info.mode, info.mtime = len(data), mode, 0
            info.uid = info.gid = 0
            info.uname = info.gname = 'root'
            tar.addfile(info, io.BytesIO(data))
    return gzip.compress(stream.getvalue(), mtime=0)

control = b'''Package: dcpt230-portable
Version: 0.2.0
Architecture: all
Maintainer: DCP-T230 portable driver project
Depends: python3 (>= 3.6), ghostscript, cups, cups-filters
Section: text
Priority: optional
Description: Experimental portable Brother DCP-T230 color printer filter
 Native Python PJL/PWG implementation for ARMv6, ARMv7 and other Linux CPUs.
 Physical printer validation is required.
'''
data = archive([
    ('usr/lib/cups/filter/dcpt230-arm', (ROOT/'src/dcpt230_filter.py').read_bytes(), 0o755),
    ('usr/share/ppd/dcpt230-arm.ppd', (ROOT/'src/dcpt230-arm.ppd').read_bytes(), 0o644),
    ('usr/share/doc/dcpt230-portable/README.md', (ROOT/'README.md').read_bytes(), 0o644),
    ('usr/share/doc/dcpt230-portable/copyright', (ROOT/'LICENSE').read_bytes(), 0o644),
    ('usr/share/doc/dcpt230-portable/NOTICE', (ROOT/'NOTICE').read_bytes(), 0o644),
])
output = ROOT/'dist/dcpt230-portable_0.2.0_all.deb'
output.parent.mkdir(exist_ok=True)
with output.open('wb') as dest:
    dest.write(b'!<arch>\n')
    for name, payload in [('debian-binary', b'2.0\n'),
                          ('control.tar.gz', archive([('control', control, 0o644)])),
                          ('data.tar.gz', data)]:
        dest.write(('%-16s%-12s%-6s%-6s%-8s%-10s`\n' %
                    (name+'/', '0', '0', '0', '100644', len(payload))).encode())
        dest.write(payload)
        if len(payload) % 2:
            dest.write(b'\n')
print(output)
