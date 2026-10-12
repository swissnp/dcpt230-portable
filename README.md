# Portable Brother DCP-T230 printer driver

An independent CUPS 2.x driver written in Rust. It renders PDF/PostScript with
Ghostscript and emits PJL-wrapped PWG Raster without the manufacturer's x86
executables or runtime CPU emulation. Not affiliated with or endorsed by Brother.

## Features

- 300 dpi color and true 8-bit grayscale; simplex, automatic tray selection.
- A4, Letter, Legal, A5 and A6; Plain, Inkjet, Glossy and Recycled media.
- Draft, Normal and Fine settings (all rendered at 300 dpi).
- Lossless pixel/scanline compression, collated copies and bounded encoder memory.
- Optional render cache with size limits, expiration and corruption checks.
- CUPS status reporting; USB status depends on interface ownership.
- Static Linux builds for 13 CPU/ABI targets; an older Python color implementation.

Scanning, duplex, borderless printing, per-page media changes and reliable ink
level reporting are not implemented. Alternative paper/media settings have not
been physically verified. This uses the traditional CUPS 2.x PPD/filter workflow.

## Choose a build

| Computer / OS | Build |
|---|---|
| ARMv6 Linux with hard-float runtime dependencies | `armv6_armhf` |
| ARMv7 Linux, 32-bit OS | `armv7_armhf` |
| ARMv5 Linux, soft-float | `armv5_armel` |
| ARMv6 / ARMv7 Linux, soft-float | `armv6_armel` / `armv7_armel` |
| ARM64 Linux, including Pi Zero 2 W with a 64-bit OS | `arm64` |
| x86_64 Linux | `amd64` |
| 32-bit x86 Linux, Pentium / Pentium 4 or newer | `i586_i386` / `i686_i386` |
| RISC-V 64 Linux (RV64GC) | `riscv64` |
| PowerPC64 Linux, big / little endian | `ppc64` / `ppc64el` |
| LoongArch64 Linux (LP64D, LSX) | `loong64` |

The ARM hard-float packages share Debian architecture `armhf`; choose by CPU. ARM1176
emulation passed, but the original Pi/Zero W has not had a hardware test.
Both ARM builds ran successfully on a real Zero 2 W, and its normal CUPS color
job printed correctly. The additional targets have CI build and QEMU regression
jobs; physical printing on those platforms remains unverified. CUPS and
Ghostscript must also support your CPU and operating system.

The build catalogue covers Rust tier 1/2 Linux musl targets with official
standard libraries. Tier 3 architectures (such as MIPS and s390x musl) require
custom toolchains and are outside this build set. See the
[Rust platform table](https://doc.rust-lang.org/rustc/platform-support.html).

## Build and install

Build on x86_64 Linux with Rust 1.99.0 and its official musl targets:

```sh
rustup toolchain install 1.99.0 --profile minimal --component rust-docs
rustup target add --toolchain 1.99.0 $(python3 tools/rust_targets.py)
export RUSTUP_TOOLCHAIN=1.99.0
sh tools/build_rust.sh
python3 tools/collect_binary_notices.py
python3 tools/build_rust_deb.py
```

Generated packages are in `dist/`; build outputs are excluded from source archives.
To build and package one target, pass its Rust triple to `tools/build_rust.sh`
and use `--target TRIPLE` with `tools/run_arm_regression.py` and
`tools/build_rust_deb.py`. CI uploads a separate artifact for each target,
including the static filter, Debian package, license notices and source archive.
For an ARMv6 Linux system:

```sh
sudo apt install ./dist/dcpt230-portable-rust_0.4.0_armv6_armhf.deb
lpinfo -v
sudo lpadmin -p DCP_T230 -E -v 'usb://Brother/REPLACE_WITH_ACTUAL_URI' \
  -P /usr/share/ppd/dcpt230-rust.ppd
lp -d DCP_T230 -o PageSize=A4 document.pdf
lp -d DCP_T230 -o BRMonoColor=Mono document.pdf
```

For LAN sharing, enable Avahi and run `sudo cupsctl --share-printers` and
`sudo lpadmin -p DCP_T230 -o printer-is-shared=true`. Clients can use
`ipp://SERVER:631/printers/DCP_T230`.

Run `dcpt230-status DCP_T230` for queue status. Optional `--usb` reads port flags
without claiming the interface; it may be unavailable when a kernel driver
owns the device. Ink levels are unavailable unless supplied by CUPS.

Render caching is off by default. Set `DCPT230_CACHE_DIR` to an absolute,
private directory owned by the filter user, then select `-o BRCache=On`.
For CUPS, provide that variable through `SetEnv` in `cups-files.conf` and
restart CUPS. Limits are 64 MiB per entry, 256 MiB total, 128 entries and 24 hours.
Unavailable/corrupt cache entries fall back to rendering. Use `BRCache=Off`
after changing fonts or rendering resources without updating Ghostscript.

Remove a queue/package with `sudo lpadmin -x DCP_T230` and
`sudo apt remove dcpt230-portable-rust`.

## Validation and performance

On Linux, install Ghostscript, libcups, Python 3 and qemu-user-static, then run:

```sh
python3 -m unittest discover -s tests -v
python3 tools/run_arm_regression.py
```

The CPU suite requires binaries produced by the build script. It runs Rust unit
and executable tests on each target (using QEMU for non-native CPUs), independently decodes
rasters with libcups, and checks pixels, packet limits, grayscale, cache behavior
and errors. No vendor software or printer is needed. Linux-specific executable
tests are skipped on macOS; the CI suite runs them on Linux.

Physical checks covered color, grayscale, multiple pages and copies on DCP-T230.
See [CONTRIBUTING.md](CONTRIBUTING.md) for development and release preparation.

Brother's official Linux driver 3.6.1-1 versus the published Rust 0.4 build,
measured on 2026-10-12 on an AMD Ryzen 9 5900X Linux server. Values are
seven-run medians after one warmup per driver; execution order alternates.
Both drivers use identical inputs and A4 color settings at 300 dpi, with
render caching disabled. Decoded raster headers and pixels matched in every test.

| Fixture | Official Brother | Portable Rust | Speedup |
|---|---:|---:|---:|
| Blank A4 encoding | 75.8 ms | 13.9 ms | **5.46×** |
| Text/color A4 encoding | 76.3 ms | 15.7 ms | **4.88×** |
| Random-noise A4 encoding | 96.1 ms | 35.5 ms | **2.71×** |
| Two-page PDF with the same renderer | 228.5 ms | 100.3 ms | **2.28×** |

Encoding tests include process startup and file I/O. The PDF test uses the
same Ghostscript renderer for both encoders, rather than Brother's CUPS
wrapper. CUPS delivery, network/USB transfer and mechanical printing are
excluded. These measurements do not establish Pi performance or physical
printing speed.

Median peak encoder memory was approximately 28 MiB for Brother versus
0.4–0.6 MiB for Rust. Including rendering, both used approximately 27–28 MiB.
Timings vary by document and system load.

Raw trials, CPU time, memory usage and binary hashes are recorded in
[the benchmark results](results/official-performance-2026-10-12.json).
Reproduce on an x86_64 Linux host with Ghostscript, libcups, Python 3 and GNU
time installed, using a locally supplied Brother driver directory:

```sh
python3 tools/benchmark_official.py --vendor-dir /opt/brother/Printers/dcpt230
```

## License

New project code and documentation are licensed under [MIT](LICENSE).
See [NOTICE](NOTICE) for attribution and third-party boundaries. Original Brother
packages, extracted executables, disassembly and local print documents are
excluded from the public source. This setup has not published a repository.
