#!/usr/bin/env bash
set -Eeuo pipefail
trap 'echo "Build failed at line $LINENO" >&2' ERR

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"
API=29
JOBS=${JOBS:-$(nproc)}
PREFIX="$ROOT/.work/prefix/android-$API"
OUT="$ROOT/dist/android-arm64"
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
export CC="$TOOLCHAIN/bin/aarch64-linux-android${API}-clang"
export CXX="$TOOLCHAIN/bin/aarch64-linux-android${API}-clang++"
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
HOST=aarch64-linux-android

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
    ./Configure android-arm64 -D__ANDROID_API__="$API" \
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

build_jq() {
  python3 scripts/prepare-sources.py jq
  local jqsrc
  jqsrc="$ROOT/$(source_path jq)"
  (
    cd "$jqsrc"
    LDFLAGS="$LDFLAGS -static" ./configure --host="$HOST" \
      --prefix="$PREFIX" --disable-shared --enable-static \
      --with-oniguruma=builtin --disable-docs --disable-maintainer-mode
    rm -f jq
    make -j"$JOBS" LDFLAGS="$LDFLAGS -all-static"
    install -m 755 jq "$OUT/bin/jq"
  )
  cp "$jqsrc/COPYING" "$OUT/licenses/jq.txt"
  cp "$jqsrc/vendor/oniguruma/COPYING" "$OUT/licenses/oniguruma.txt"
}

if [[ $# == 0 ]]; then set -- curl; fi
for tool in "$@"; do
  case "$tool" in
    curl) build_curl ;;
    jq) build_jq ;;
    *) echo "Unknown tool: $tool (supported: curl jq)" >&2; exit 2 ;;
  esac
done

for binary in "$OUT"/bin/*; do
  "$STRIP" --strip-unneeded "$binary"
  report="$OUT/$(basename "$binary").elf.txt"
  "$TOOLCHAIN/bin/llvm-readelf" -h -l -d "$binary" > "$report"
  if ! grep -q 'Machine:.*AArch64' "$report"; then
    echo "Incorrect architecture: $binary" >&2; exit 1
  fi
  if grep -Eq 'NEEDED|INTERP' "$report"; then
    echo "Unexpected dynamic dependency: $binary" >&2; exit 1
  fi
done
cp "$ANDROID_NDK_HOME/toolchains/llvm/prebuilt/linux-x86_64/NOTICE" "$OUT/licenses/NDK-NOTICE.txt"
python3 scripts/package.py
