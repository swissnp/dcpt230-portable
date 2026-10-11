#!/usr/bin/env python3
"""Collect redistribution notices for the toolchain used to build static releases."""
import argparse
from pathlib import Path
import shutil
import subprocess
import urllib.request

ROOT = Path(__file__).resolve().parents[1]

def collect(rustc='rustc', musl_copyright=None):
    sysroot = Path(subprocess.check_output([rustc, '--print', 'sysroot'], text=True).strip())
    directory = ROOT / 'dist/rust/notices'
    directory.mkdir(parents=True, exist_ok=True)
    # Preserve the full bundle, including standard-library dependency notices.
    copyright = sysroot / 'share/doc/rust/COPYRIGHT.html'
    if not copyright.is_file():
        raise RuntimeError('Missing toolchain COPYRIGHT.html; install rust-docs for this toolchain')
    shutil.copyfile(copyright, directory / 'RUST-COPYRIGHT.html')
    if musl_copyright:
        payload = Path(musl_copyright).read_bytes()
    else:
        url = 'https://git.musl-libc.org/cgit/musl/plain/COPYRIGHT'
        with urllib.request.urlopen(url, timeout=30) as response:
            payload = response.read(256 * 1024 + 1)
    if len(payload) > 256 * 1024 or b'Permission' not in payload or b'Copyright' not in payload:
        raise RuntimeError('Invalid musl COPYRIGHT document')
    (directory / 'MUSL-COPYRIGHT').write_bytes(payload)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rustc', default='rustc')
    parser.add_argument('--musl-copyright', help='Use a locally obtained musl COPYRIGHT instead of downloading')
    args = parser.parse_args()
    collect(args.rustc, args.musl_copyright)
