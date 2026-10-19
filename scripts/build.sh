#!/usr/bin/env bash
set -Eeuo pipefail
trap 'echo "Build failed at line $LINENO" >&2' ERR

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"
ARCH=${ARCH:-arm64}
API=$(python3 -c 'import json; print(json.load(open("build-list.json"))["android_api"])')
if [[ $# == 0 ]]; then set -- ripgrep stress curl; fi
python3 scripts/catalog.py plan --tools "$*" --architectures "$ARCH" > /dev/null
arch_field() { python3 scripts/catalog.py arch --arch "$ARCH" --field "$1"; }
CLANG_TARGET=$(arch_field clang)
HOST=$(arch_field host)
OPENSSL_TARGET=$(arch_field openssl)
RUST_TARGET=$(arch_field rust)
RUST_VERSION=$(python3 scripts/catalog.py rust-version)
JOBS=${JOBS:-$(nproc)}
PREFIX="$ROOT/.work/prefix/$ARCH-android-$API"
OUT="$ROOT/dist/android-$ARCH"
mkdir -p "$PREFIX" "$OUT/bin" "$OUT/licenses"

source_path() {
  python3 -c 'import json,sys; print(".work/" + json.load(open("sources.json"))[sys.argv[1]]["directory"])' "$1"
}

if [[ -z ${ANDROID_NDK_HOME:-} ]]; then
  python3 scripts/prepare-sources.py ndk
  ANDROID_NDK_HOME="$ROOT/$(source_path ndk)"
fi
export ANDROID_NDK_HOME
export ANDROID_NDK_ROOT="$ANDROID_NDK_HOME"
TOOLCHAIN="$ANDROID_NDK_HOME/toolchains/llvm/prebuilt/linux-x86_64"
export PATH="$TOOLCHAIN/bin:$PATH"
export CC="$TOOLCHAIN/bin/${CLANG_TARGET}${API}-clang"
export CXX="$TOOLCHAIN/bin/${CLANG_TARGET}${API}-clang++"
export AR="$TOOLCHAIN/bin/llvm-ar"
export RANLIB="$TOOLCHAIN/bin/llvm-ranlib"
export STRIP="$TOOLCHAIN/bin/llvm-strip"
export NM="$TOOLCHAIN/bin/llvm-nm"
export CFLAGS='-O2 -fPIC -ffunction-sections -fdata-sections'
export CPPFLAGS="-I$PREFIX/include"
export LDFLAGS="-L$PREFIX/lib -Wl,-z,max-page-size=16384 -Wl,--gc-sections"
export PKG_CONFIG_LIBDIR="$PREFIX/lib/pkgconfig"
export PKG_CONFIG_PATH="$PKG_CONFIG_LIBDIR"
export PKG_CONFIG_ALLOW_CROSS=1

build_curl() {
  python3 scripts/prepare-sources.py curl openssl nghttp2 zlib cacert
  local ssl zlib http2 curlsrc
  ssl="$ROOT/$(source_path openssl)"
  zlib="$ROOT/$(source_path zlib)"
  http2="$ROOT/$(source_path nghttp2)"
  curlsrc="$ROOT/$(source_path curl)"
  (
    cd "$ssl"
    export CC=clang CXX=clang++
    ./Configure "$OPENSSL_TARGET" -D__ANDROID_API__="$API" \
      --prefix="$PREFIX" --libdir=lib \
      no-shared no-tests no-apps no-module no-dso no-legacy no-autoload-config
    make -j"$JOBS" build_libs
    make install_dev
  )
  (
    cd "$zlib"
    ./configure --static --prefix="$PREFIX"
    make -j"$JOBS"
    make install
  )
  (
    cd "$http2"
    ./configure --host="$HOST" --prefix="$PREFIX" \
      --enable-lib-only --disable-shared --enable-static
    make -j"$JOBS"
    make install
  )
  (
    cd "$curlsrc"
    # New NDK static libc exports memset_explicit, but API 29 headers do not
    # declare it. Select curl's secure fallback rather than the link-only probe.
    ac_cv_func_memset_explicit=no LDFLAGS="$LDFLAGS -static" LIBS='-ldl -lm' \
    ./configure --host="$HOST" --prefix="$PREFIX" \
      --disable-shared --enable-static \
      --with-openssl="$PREFIX" --with-nghttp2="$PREFIX" --with-zlib="$PREFIX" \
      --with-ca-embed="$ROOT/.work/downloads/cacert.pem" \
      --without-ca-bundle --without-ca-path \
      --without-libpsl --without-libidn2 --without-brotli --without-zstd \
      --without-libssh --without-libssh2 --without-gssapi \
      --without-nghttp3 --without-ngtcp2 --without-quiche \
      --disable-ldap --disable-ldaps --disable-manual \
      --enable-threaded-resolver
    # libtool's -static only selects static third-party libraries; -all-static
    # also selects the NDK's static C runtime for the final executable.
    rm -f src/curl
    make -j"$JOBS" LDFLAGS="$LDFLAGS -all-static"
    install -m 755 src/curl "$OUT/bin/curl"
  )
  cp "$curlsrc/COPYING" "$OUT/licenses/curl.txt"
  cp "$ssl/LICENSE.txt" "$OUT/licenses/OpenSSL.txt"
  cp "$http2/COPYING" "$OUT/licenses/nghttp2.txt"
  cp "$zlib/LICENSE" "$OUT/licenses/zlib.txt"
  cp "$ROOT/.work/downloads/cacert.pem" "$OUT/cacert.pem"
}

build_stress() {
  python3 scripts/prepare-sources.py stress
  local stresssrc
  stresssrc="$ROOT/$(source_path stress)"
  (
    cd "$stresssrc"
    # Bionic's malloc(0) returns an allocation. Autoconf cannot run this probe
    # while cross-compiling and otherwise selects a nonexistent rpl_malloc.
    ac_cv_func_malloc_0_nonnull=yes LDFLAGS="$LDFLAGS -static" ./configure --host="$HOST" \
      --prefix="$PREFIX"
    make -j"$JOBS"
    install -m 755 src/stress "$OUT/bin/stress"
  )
  cp "$stresssrc/COPYING" "$OUT/licenses/stress.txt"
  # Distribute the exact corresponding GPL source together with its binaries.
  mkdir -p "$OUT/sources"
  cp "$ROOT/.work/downloads/$(basename "$stresssrc").tar.gz" "$OUT/sources/"
}

build_ripgrep() {
  python3 scripts/prepare-sources.py ripgrep
  local rgsrc linker_key builtins
  rgsrc="$ROOT/$(source_path ripgrep)"
  rustup toolchain install "$RUST_VERSION" --profile minimal --no-self-update
  rustup target add --toolchain "$RUST_VERSION" "$RUST_TARGET"
  linker_key="CARGO_TARGET_${RUST_TARGET^^}_LINKER"
  linker_key=${linker_key//-/_}
  # Rust uses -nodefaultlibs. Bionic's x86 CPU dispatch still needs compiler-rt,
  # which the Clang driver would normally add to a C executable itself.
  builtins=$("$CC" --print-libgcc-file-name)
  test -f "$builtins"
  (
    cd "$rgsrc"
    export "$linker_key=$CC"
    export RUSTFLAGS="-C target-feature=+crt-static -C relocation-model=static -C link-arg=-static -C link-arg=-Wl,-z,max-page-size=16384 -C panic=abort -C link-arg=$builtins"
    cargo +"$RUST_VERSION" build --locked --release --target "$RUST_TARGET" --bin rg -j "$JOBS"
    install -m 755 "target/$RUST_TARGET/release/rg" "$OUT/bin/rg"
    cargo +"$RUST_VERSION" metadata --locked --format-version 1 --filter-platform "$RUST_TARGET" |
      python3 "$ROOT/scripts/collect-rust-licenses.py" "$OUT/licenses/rust" "$(rustup run "$RUST_VERSION" rustc --print sysroot)"
  )
}

for tool in "$@"; do
  case "$tool" in
    curl) build_curl ;;
    stress) build_stress ;;
    ripgrep) build_ripgrep ;;
    *) echo "Unknown tool: $tool" >&2; exit 2 ;;
  esac
done

for binary in "$OUT"/bin/*; do
  "$STRIP" --strip-unneeded "$binary"
  report="$OUT/$(basename "$binary").elf.txt"
  "$TOOLCHAIN/bin/llvm-readelf" -h -l -d "$binary" > "$report"
  python3 scripts/verify-elf.py "$binary" "$ARCH"
  if grep -Eq 'NEEDED|INTERP' "$report"; then
    echo "Unexpected dynamic dependency: $binary" >&2; exit 1
  fi
done
cp "$ANDROID_NDK_HOME/toolchains/llvm/prebuilt/linux-x86_64/NOTICE" "$OUT/licenses/NDK-NOTICE.txt"
python3 scripts/package.py --arch "$ARCH" --tools "$*"
