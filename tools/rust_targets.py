#!/usr/bin/env python3
"""Shared Linux static build, package and emulation target catalogue."""
import json
import sys

# Rust tier 1/2 Linux musl targets with distributed standard libraries.
TARGETS = {
    'x86_64-unknown-linux-musl': dict(arch='amd64', label='amd64', runner=[]),
    'i586-unknown-linux-musl': dict(arch='i386', label='i586_i386', runner=['qemu-i386-static', '-cpu', 'pentium']),
    'i686-unknown-linux-musl': dict(arch='i386', label='i686_i386', runner=['qemu-i386-static']),
    'armv5te-unknown-linux-musleabi': dict(arch='armel', label='armv5_armel', runner=['qemu-arm-static', '-cpu', 'arm926']),
    'arm-unknown-linux-musleabi': dict(arch='armel', label='armv6_armel', runner=['qemu-arm-static', '-cpu', 'arm1176']),
    'arm-unknown-linux-musleabihf': dict(arch='armhf', label='armv6_armhf', runner=['qemu-arm-static', '-cpu', 'arm1176']),
    'armv7-unknown-linux-musleabi': dict(arch='armel', label='armv7_armel', runner=['qemu-arm-static', '-cpu', 'cortex-a7']),
    'armv7-unknown-linux-musleabihf': dict(arch='armhf', label='armv7_armhf', runner=['qemu-arm-static', '-cpu', 'cortex-a7']),
    'aarch64-unknown-linux-musl': dict(arch='arm64', label='arm64', runner=['qemu-aarch64-static']),
    'riscv64gc-unknown-linux-musl': dict(arch='riscv64', label='riscv64', runner=['qemu-riscv64-static']),
    'powerpc64-unknown-linux-musl': dict(arch='ppc64', label='ppc64', runner=['qemu-ppc64-static']),
    'powerpc64le-unknown-linux-musl': dict(arch='ppc64el', label='ppc64el', runner=['qemu-ppc64le-static']),
    'loongarch64-unknown-linux-musl': dict(arch='loong64', label='loong64', runner=['qemu-loongarch64-static']),
}

if __name__ == "__main__":
    if sys.argv[1:] == ["--matrix"]:
        print(json.dumps({"target": list(TARGETS)}))
    else:
        print(" ".join(TARGETS))
