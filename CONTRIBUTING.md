# Contributing

Contributions to newly written code are accepted under the MIT license.
Keep vendor executables, extracted code, personal documents, printer serials,
credentials and deployment addresses out of pull requests.

## Development

The filter has no Cargo dependencies. `cargo test --manifest-path rust/Cargo.toml`
runs native Rust unit tests. The cross-build script runs on x86_64 Linux and
builds the targets listed in `tools/rust_targets.py` using the installed rustup
toolchain and bundled linker. See README for setup.
Install Ghostscript, libcups, Python 3 and qemu-user-static on Linux, then run
`python3 tools/run_arm_regression.py` after building.

Generate synthetic benchmark documents with
`python3 tools/generate_test_documents.py`. Benchmarks do not submit print jobs.
Reports should identify CPU, OS, driver version, trial count and measured stages.

Regression tests are self-contained and require no manufacturer software.
Private documentation and research artifacts are excluded from distributions.

## Release preparation

1. Run cross-architecture regression with no vendor files present.
2. Build packages from the same source revision; never reuse old binaries.
3. Include LICENSE, NOTICE, the Rust toolchain copyright bundle, and musl's
   COPYRIGHT in binary packages. The builder requires these notices.
4. Record independent raster checks and physical printer checks. Emulation
   does not establish real-board performance or physical print behavior.
5. Run `python3 tools/prepare_source_release.py` and inspect its file manifest.

The source exporter uses an explicit file allowlist and produces a SHA-256
checksum. Git ignore rules are an additional safeguard. The CI workflow
builds, tests and prepares artifacts; it does not publish a release.

## Bug reports

Include model, CPU architecture, OS, package version, selected options,
queue state and a minimal synthetic reproducer. Remove serial numbers,
document contents and deployment addresses from logs.
