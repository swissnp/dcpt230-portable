#!/usr/bin/env python3
"""Package tested Rust binaries without requiring dpkg-deb locally."""
import gzip
import argparse
import io
from pathlib import Path
import tarfile

ROOT=Path(__file__).resolve().parents[1]

def archive(files):
    stream=io.BytesIO()
    with tarfile.open(fileobj=stream,mode='w',format=tarfile.USTAR_FORMAT) as tar:
        directories=set()
        for name,_,_ in files:
            for parent in Path(name).parents:
                if str(parent)!='.':directories.add(str(parent))
        for name in sorted(directories,key=lambda n:(n.count('/'),n)):
            info=tarfile.TarInfo(name+'/');info.type=tarfile.DIRTYPE;info.mode=0o755
            info.uid=info.gid=info.mtime=0;info.uname=info.gname='root';tar.addfile(info)
        for name,data,mode in files:
            info=tarfile.TarInfo(name);info.size=len(data);info.mode=mode
            info.uid=info.gid=info.mtime=0;info.uname=info.gname='root'
            tar.addfile(info,io.BytesIO(data))
    return gzip.compress(stream.getvalue(),mtime=0)

ppd=(ROOT/'src/dcpt230-arm.ppd').read_text().replace('dcpt230-arm','dcpt230-rust')
ppd=ppd.replace('*FileVersion: "0.2"','*FileVersion: "0.4"')
ppd=ppd.replace('T230PY.PPD','T230RS.PPD')
ppd=ppd.replace('DCP-T230 portable Python','DCP-T230 portable Rust')
ppd=ppd.replace('*ShortNickName: "DCP-T230 portable"','*ShortNickName: "DCP-T230 Rust"')
ppd+='\n*OpenUI *BRMonoColor/Color Mode: PickOne\n*OrderDependency: 20 AnySetup *BRMonoColor\n*DefaultBRMonoColor: FullColor\n*BRMonoColor FullColor/Color: ""\n*BRMonoColor Mono/Grayscale: ""\n*CloseUI: *BRMonoColor\n*OpenUI *BRCache/Reuse Rendered Jobs: PickOne\n*OrderDependency: 20 AnySetup *BRCache\n*DefaultBRCache: Off\n*BRCache Off/Off: ""\n*BRCache On/On: ""\n*CloseUI: *BRCache\n'
targets={
    'x86_64-unknown-linux-musl':('amd64','amd64'),
    'arm-unknown-linux-musleabihf':('armhf','armv6_armhf'),
    'armv7-unknown-linux-musleabihf':('armhf','armv7_armhf'),
}
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument("--target",choices=tuple(targets),help="Package one already built target")
args=parser.parse_args()
notice_dir=ROOT/'dist/rust/notices'
for name in ('RUST-COPYRIGHT.html','MUSL-COPYRIGHT'):
    if not (notice_dir/name).is_file():
        parser.error('Missing binary notices; run tools/collect_binary_notices.py with the build toolchain first')
for target,(arch,label) in targets.items():
    if args.target and target!=args.target:continue
    binary=ROOT/'dist/rust'/('dcpt230-rust-'+target)
    control=('Package: dcpt230-portable-rust\nVersion: 0.4.0\nArchitecture: '+arch+'''
Maintainer: DCP-T230 portable driver project
Depends: ghostscript, cups, cups-filters
Recommends: python3, libusb-1.0-0
Section: text
Priority: optional
Description: Portable Rust Brother DCP-T230 color and grayscale printer filter
 Native PJL/PWG implementation with no Python or Intel binary requirement.
''').encode()
    data=archive([
        ('usr/lib/cups/filter/dcpt230-rust',binary.read_bytes(),0o755),
        ('usr/share/ppd/dcpt230-rust.ppd',ppd.encode(),0o644),
        ('usr/share/doc/dcpt230-portable-rust/README.md',(ROOT/'README.md').read_bytes(),0o644),
        ('usr/bin/dcpt230-status',(ROOT/'tools/printer_status.py').read_bytes(),0o755),
        ('usr/share/doc/dcpt230-portable-rust/copyright',(ROOT/'LICENSE').read_bytes(),0o644),
        ('usr/share/doc/dcpt230-portable-rust/NOTICE',(ROOT/'NOTICE').read_bytes(),0o644),
        ('usr/share/doc/dcpt230-portable-rust/RUST-COPYRIGHT.html',(notice_dir/'RUST-COPYRIGHT.html').read_bytes(),0o644),
        ('usr/share/doc/dcpt230-portable-rust/MUSL-COPYRIGHT',(notice_dir/'MUSL-COPYRIGHT').read_bytes(),0o644),
    ])
    output=ROOT/'dist'/('dcpt230-portable-rust_0.4.0_'+label+'.deb')
    with output.open('wb') as dest:
        dest.write(b'!<arch>\n')
        for name,payload in [('debian-binary',b'2.0\n'),
                ('control.tar.gz',archive([('control',control,0o644)])),('data.tar.gz',data)]:
            dest.write(('%-16s%-12s%-6s%-6s%-8s%-10s`\n'%
                       (name+'/',0,0,0,'100644',len(payload))).encode())
            dest.write(payload)
            if len(payload)%2:dest.write(b'\n')
    print(output)
