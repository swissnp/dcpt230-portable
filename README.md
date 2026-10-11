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
- Native amd64, ARMv6 and ARMv7 builds; an older Python color implementation.

Scanning, duplex, borderless printing, per-page media changes and reliable ink
level reporting are not implemented. Alternative paper/media settings have not
been physically verified. This uses the traditional CUPS 2.x PPD/filter workflow.

## Choose a build

| Computer / OS | Build |
|---|---|
| ARMv6 Linux with hard-float runtime dependencies | `armv6_armhf` |
| ARMv7 Linux, 32-bit OS | `armv7_armhf` |
| x86_64 Linux | `amd64` |

Both ARM packages have Debian architecture `armhf`; choose by CPU. ARM1176
emulation passed, but the original Pi/Zero W has not had a hardware test.
Both ARM builds ran successfully on a real Zero 2 W, and its normal CUPS color
job printed correctly. No native aarch64 release is provided. CUPS and Ghostscript
must also support your CPU and operating system.

## Build and install

Build on x86_64 Linux with Rust 1.99.0 and its official musl targets:

```sh
rustup toolchain install 1.99.0 --profile minimal --component rust-docs
rustup target add --toolchain 1.99.0 x86_64-unknown-linux-musl arm-unknown-linux-musleabihf armv7-unknown-linux-musleabihf
export RUSTUP_TOOLCHAIN=1.99.0
sh tools/build_rust.sh
python3 tools/collect_binary_notices.py
python3 tools/build_rust_deb.py
```

Generated packages are in `dist/`; build outputs are excluded from source archives.
For an ARMv6 Linux system:

```sh
sudo apt install ./dist/dcpt230-portable-rust_0.4.0_armv6_armhf.deb
lpinfo -v
sudo lpadmin -p DCP_T230 -E -v 'usb://Brother/REPLACE_WITH_ACTUAL_URI' \
  -P /usr/share/ppd/dcpt230-rust.ppd
lp -d DCP_T230 -o PageSize=A4 document.pdf
lp -d DCP_T230 -o BRMonoColor=Mono document.pdf
```

If USB jobs complete without printing, the Linux `usblp` kernel driver can be
used with CUPS's `parallel` backend. Customize the serial number in
`tools/99-dcpt230-usblp.rules`, install it in `/etc/udev/rules.d/`, reload udev
rules, and reconnect the printer. Then set the queue device with:

```sh
sudo lpadmin -p DCP_T230 -v parallel:/dev/dcpt230 -E
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

The ARM suite requires binaries produced by the build script. It runs Rust unit
and executable tests on x86_64, ARM1176 and Cortex-A7, independently decodes
rasters with libcups, and checks pixels, packet limits, grayscale, cache behavior
and errors. No vendor software or printer is needed. Linux-specific executable
tests are skipped on macOS; the CI suite runs them on Linux.

Physical checks covered color, grayscale, multiple pages and copies on DCP-T230.
See [CONTRIBUTING.md](CONTRIBUTING.md) for development and release preparation.

Three-run median processing times, excluding mechanical printing:

| Fixture | AMD x86_64, Rust 0.3 | Pi Zero 2 W, Rust 0.4 |
|---|---:|---:|
| Text/color raster encoding | 0.201 s | 0.210 s |
| Two-page PDF, rendering and encoding | 0.877 s | 1.045 s |

These were separate sessions and builds, not a controlled CPU comparison.
The Pi's optimized Python baseline took 2.141 s for the complete PDF job.
The measured complete job peaked at approximately 28 MB RAM on both hosts.

## License

New project code and documentation are licensed under [MIT](LICENSE).
See [NOTICE](NOTICE) for attribution and third-party boundaries. Original Brother
packages, extracted executables, disassembly and local print documents are
excluded from the public source. This setup has not published a repository.
