#!/bin/sh
set -eu
T230_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
T230_RUSTC=${RUSTC:-rustc}
if ! command -v "$T230_RUSTC" >/dev/null 2>&1; then
    T230_RUSTC="${CARGO_HOME:-$HOME/.cargo}/bin/rustc"
fi
T230_SYSROOT=$("$T230_RUSTC" --print sysroot)
case $("$T230_RUSTC" -vV) in
    *'host: x86_64-unknown-linux-gnu'*) ;;
    *) echo 'This cross-build script requires an x86_64 GNU/Linux Rust host.' >&2; exit 1 ;;
esac
T230_LINKER="$T230_SYSROOT/lib/rustlib/x86_64-unknown-linux-gnu/bin/rust-lld"
mkdir -p "$T230_ROOT/dist/rust"
for T230_TARGET in x86_64-unknown-linux-musl arm-unknown-linux-musleabihf armv7-unknown-linux-musleabihf; do
    if [ "$T230_TARGET" = arm-unknown-linux-musleabihf ]; then
        T230_CPU='-Ctarget-cpu=arm1176jzf-s'
    else
        T230_CPU=''
    fi
    "$T230_RUSTC" --edition=2021 --crate-name dcpt230_rust "$T230_ROOT/rust/src/main.rs" \
        --target "$T230_TARGET" -C linker="$T230_LINKER" -C link-self-contained=yes \
        -C opt-level=3 -C lto=fat -C codegen-units=1 -C panic=abort -C strip=symbols \
        $T230_CPU -o "$T230_ROOT/dist/rust/dcpt230-rust-$T230_TARGET"
    "$T230_RUSTC" --edition=2021 --test "$T230_ROOT/rust/src/main.rs" \
        --target "$T230_TARGET" -C linker="$T230_LINKER" -C link-self-contained=yes \
        -C opt-level=2 $T230_CPU -o "$T230_ROOT/dist/rust/test-$T230_TARGET"
done
"$T230_ROOT/dist/rust/test-x86_64-unknown-linux-musl"
