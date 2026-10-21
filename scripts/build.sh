#!/usr/bin/env bash
set -Eeuo pipefail
trap 'echo "Build failed at line $LINENO" >&2' ERR

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"
ARCH=${ARCH:-arm64}
API=$(python3 -c 'import json; print(json.load(open("build-list.json"))["android_api"])')
if [[ $# == 0 ]]; then read -r -a defaults <<< "$(python3 -c 'import json; print(" ".join(json.load(open("build-list.json"))["tools"]))')"; set -- "${defaults[@]}"; fi
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
export MAKEFLAGS="${MAKEFLAGS:-} --no-print-directory --silent"

build_crypto() {
  [[ -f "$PREFIX/lib/libssl.a" ]] && return
  python3 scripts/prepare-sources.py openssl
  local ssl
  ssl="$ROOT/$(source_path openssl)"
  (
    cd "$ssl"
    export CC=clang CXX=clang++
    ./Configure "$OPENSSL_TARGET" -D__ANDROID_API__="$API" \
      --prefix="$PREFIX" --libdir=lib \
      no-shared no-tests no-apps no-module no-dso enable-legacy no-autoload-config
    make -j"$JOBS" build_libs
    make install_dev
  )
  cp "$ssl/LICENSE.txt" "$OUT/licenses/OpenSSL.txt"
}

build_zlib() {
  [[ -f "$PREFIX/lib/libz.a" ]] && return
  python3 scripts/prepare-sources.py zlib
  local zlib
  zlib="$ROOT/$(source_path zlib)"
  (
    cd "$zlib"
    ./configure --static --prefix="$PREFIX"
    make -j"$JOBS"
    make install
  )
  cp "$zlib/LICENSE" "$OUT/licenses/zlib.txt"
}

build_curl() {
  python3 scripts/prepare-sources.py curl nghttp2 cacert
  build_crypto
  build_zlib
  local http2 curlsrc
  http2="$ROOT/$(source_path nghttp2)"
  curlsrc="$ROOT/$(source_path curl)"
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
  cp "$http2/COPYING" "$OUT/licenses/nghttp2.txt"
  cp "$ROOT/.work/downloads/cacert.pem" "$OUT/cacert.pem"
}

build_jq() {
  python3 scripts/prepare-sources.py jq
  local src="$ROOT/$(source_path jq)"
  (
    cd "$src"
    LDFLAGS="$LDFLAGS -static" ./configure --host="$HOST" --prefix="$PREFIX" \
      --disable-shared --enable-static --with-oniguruma=builtin \
      --disable-docs --disable-maintainer-mode
    make -j"$JOBS" LDFLAGS="$LDFLAGS -all-static"
    install -m 755 jq "$OUT/bin/jq"
  )
  cp "$src/COPYING" "$OUT/licenses/jq.txt"
  cp "$src/vendor/oniguruma/COPYING" "$OUT/licenses/oniguruma.txt"
}

build_iperf3() {
  python3 scripts/prepare-sources.py iperf3
  local src="$ROOT/$(source_path iperf3)"
  (
    cd "$src"
    LDFLAGS="$LDFLAGS -static" ./configure --host="$HOST" --prefix="$PREFIX" \
      --disable-shared --enable-static --without-openssl
    make -j"$JOBS" LDFLAGS="$LDFLAGS -all-static"
    install -m 755 src/iperf3 "$OUT/bin/iperf3"
  )
  cp "$src/LICENSE" "$OUT/licenses/iperf3.txt"
}

build_zstd() {
  python3 scripts/prepare-sources.py zstd
  local src="$ROOT/$(source_path zstd)"
  (
    cd "$src"
    make -C programs -j"$JOBS" zstd LDFLAGS="$LDFLAGS -static" \
      ZSTD_LEGACY_SUPPORT=0 ZSTD_ZLIB_SUPPORT=0 ZSTD_LZMA_SUPPORT=0 ZSTD_LZ4_SUPPORT=0
    install -m 755 programs/zstd "$OUT/bin/zstd"
  )
  cp "$src/LICENSE" "$OUT/licenses/zstd.txt"
}

build_sqlite3() {
  python3 scripts/prepare-sources.py sqlite3
  local src="$ROOT/$(source_path sqlite3)"
  (
    cd "$src"
    "$CC" $CFLAGS $CPPFLAGS -DSQLITE_THREADSAFE=1 -DSQLITE_ENABLE_FTS5 \
      -DSQLITE_ENABLE_RTREE -DSQLITE_ENABLE_MATH_FUNCTIONS \
      -DSQLITE_ENABLE_COLUMN_METADATA -DSQLITE_OMIT_LOAD_EXTENSION \
      shell.c sqlite3.c $LDFLAGS -static -ldl -lm -o "$OUT/bin/sqlite3"
  )
  cp "$ROOT/docs/SQLITE-NOTICE.txt" "$OUT/licenses/sqlite3.txt"
}

build_socat() {
  python3 scripts/prepare-sources.py socat
  build_crypto
  local src="$ROOT/$(source_path socat)"
  (
    cd "$src"
    ac_cv_header_resolv_h=no sc_cv_getprotobynumber_r= ac_cv_have_c99_snprintf=yes \
      sc_cv_sys_crdly_shift=9 sc_cv_sys_tabdly_shift=11 sc_cv_sys_csize_shift=4 \
      LDFLAGS="$LDFLAGS -static" LIBS='-ldl -lm' ./configure \
      --host="$HOST" --prefix="$PREFIX" --disable-readline --disable-libwrap \
      --disable-posixmq --enable-openssl --enable-openssl-base="$PREFIX"
    make -j"$JOBS" socat
    install -m 755 socat "$OUT/bin/socat"
  )
  cp "$src/COPYING" "$OUT/licenses/socat.txt"
  cp "$src/COPYING.OpenSSL" "$OUT/licenses/socat-OpenSSL.txt"
}

build_aria2() {
  python3 scripts/prepare-sources.py aria2 cacert
  build_crypto
  build_zlib
  local src="$ROOT/$(source_path aria2)"
  (
    cd "$src"
    # Upstream's ARIA2_STATIC=yes adds GNU/Linux -lpthread and -lrt, whose
    # functions are part of Android libc. Request static linkage ourselves.
    ARIA2_STATIC=no LDFLAGS="$LDFLAGS -static -static-libstdc++" LIBS='-ldl -lm' \
      ./configure --host="$HOST" --prefix="$PREFIX" --disable-shared --enable-static \
      --with-openssl --with-libz --without-gnutls --without-libgcrypt \
      --without-libnettle --without-libgmp --without-libssh2 --without-libcares \
      --without-libxml2 --without-libexpat --without-sqlite3 \
      --disable-metalink --disable-nls --disable-dependency-tracking
    make -j"$JOBS" LDFLAGS="$LDFLAGS -all-static -static-libstdc++"
    install -m 755 src/aria2c "$OUT/bin/aria2c"
  )
  cp "$src/COPYING" "$OUT/licenses/aria2.txt"
  cp "$src/LICENSE.OpenSSL" "$OUT/licenses/aria2-OpenSSL.txt"
  cp "$ROOT/docs/GPL-3.0.txt" "$OUT/licenses/aria2-GPL-3.0.txt"
  cp "$ROOT/docs/ARIA2-NOTICE.txt" "$OUT/licenses/aria2-build.txt"
  cp "$ROOT/.work/downloads/cacert.pem" "$OUT/cacert.pem"
}

build_tcpdump() {
  python3 scripts/prepare-sources.py tcpdump libpcap
  local pcap="$ROOT/$(source_path libpcap)" src="$ROOT/$(source_path tcpdump)"
  (
    cd "$pcap"
    LDFLAGS="$LDFLAGS -static" ./configure --host="$HOST" --prefix="$PREFIX" \
      --disable-shared --disable-dbus --disable-bluetooth --without-libnl \
      --disable-rdma --without-dag --without-septel --without-snf --without-turbocap
    make -j"$JOBS"
    make install
  )
  (
    cd "$src"
    LDFLAGS="$LDFLAGS -static" ./configure --host="$HOST" --prefix="$PREFIX" \
      --with-crypto=no --without-cap-ng --with-user=nobody
    make -j"$JOBS"
    install -m 755 tcpdump "$OUT/bin/tcpdump"
  )
  cp "$src/LICENSE" "$OUT/licenses/tcpdump.txt"
  cp "$pcap/LICENSE" "$OUT/licenses/libpcap.txt"
}

build_strace() {
  python3 scripts/prepare-sources.py strace
  local src="$ROOT/$(source_path strace)"
  (
    cd "$src"
    patch -p1 < "$ROOT/patches/strace-android-in-addr.patch"
    CPPFLAGS="$CPPFLAGS -Dfputs_unlocked=fputs" LDFLAGS="$LDFLAGS -static" \
      ./configure --host="$HOST" --prefix="$PREFIX" --enable-mpers=no \
      --enable-stacktrace=no --without-libunwind --without-libdw \
      --without-libselinux --without-libiberty --disable-gcc-Werror
    make -j"$JOBS"
    install -m 755 src/strace "$OUT/bin/strace"
  )
  cp "$src/COPYING" "$OUT/licenses/strace.txt"
  cp "$src/LGPL-2.1-or-later" "$OUT/licenses/strace-LGPL.txt"
  cp "$src/bundled/linux/COPYING" "$OUT/licenses/strace-linux.txt"
}

build_stress_ng() {
  python3 scripts/prepare-sources.py stress-ng
  local src="$ROOT/$(source_path stress-ng)"
  (
    cd "$src"
    # Probe the target headers/libraries, never the runner's optional libraries.
    make -j"$JOBS" STATIC=1 CC="$CC" CXX="$CXX" AR="$AR" \
      LDFLAGS="$LDFLAGS -static" JOBS="$JOBS" \
      LIB_ACL= LIB_AIO= LIB_APPARMOR= LIB_BSD= LIB_CRYPT= LIB_EGL= LIB_GBM= \
      LIB_GLES2= LIB_GMP= LIB_IPSEC_MB= LIB_JPEG= LIB_JUDY= LIB_KMOD= LIB_MD= \
      LIB_MPFR= LIB_SCTP= LIB_XXHASH= LIB_Z= LIB_LZMA= LIB_FSNOTIFY= LIB_NL= LIB_GENL=
    install -m 755 stress-ng "$OUT/bin/stress-ng"
  )
  cp "$src/COPYING" "$OUT/licenses/stress-ng.txt"
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

build_busybox() {
  python3 scripts/prepare-sources.py busybox
  local src="$ROOT/$(source_path busybox)"
  (
    cd "$src"
    for fix in "$ROOT"/patches/busybox/*.patch; do patch -p1 < "$fix"; done
    local bbarch="$ARCH"
    [[ $ARCH != armv7 ]] || bbarch=arm
    [[ $ARCH != x86 ]] || bbarch=i386
    local -a options=(ARCH="$bbarch" CC="$CC" HOSTCC=gcc AR="$AR" NM="$NM"
      STRIP="$STRIP" OBJCOPY="$TOOLCHAIN/bin/llvm-objcopy" OBJDUMP="$TOOLCHAIN/bin/llvm-objdump"
      SKIP_STRIP=y)
    make "${options[@]}" defconfig
    python3 "$ROOT/scripts/configure-busybox.py" "$src"
    make "${options[@]}" oldconfig </dev/null
    make -k -j"$JOBS" "${options[@]}"
    install -m 755 busybox_unstripped "$OUT/bin/busybox"
    python3 "$ROOT/scripts/configure-busybox.py" "$src" record
  )
  cp "$src/LICENSE" "$OUT/licenses/busybox.txt"
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

if [[ ${BUILD_MODE:-all} != package ]]; then
for tool in "$@"; do
  case "$tool" in
    curl) build_curl ;;
    stress) build_stress ;;
    ripgrep) build_ripgrep ;;
    jq) build_jq ;;
    iperf3) build_iperf3 ;;
    zstd) build_zstd ;;
    sqlite3) build_sqlite3 ;;
    socat) build_socat ;;
    aria2) build_aria2 ;;
    tcpdump) build_tcpdump ;;
    strace) build_strace ;;
    stress-ng) build_stress_ng ;;
    busybox) build_busybox ;;
    *) echo "Unknown tool: $tool" >&2; exit 2 ;;
  esac
done
fi
if [[ ${BUILD_MODE:-all} == compile ]]; then exit 0; fi

python3 scripts/retain-sources.py "$OUT" "$@"

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
