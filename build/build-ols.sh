#!/bin/bash
set -eo pipefail

OLS_TAG=v1.9.4
OLS_COMMIT=aeba673f6cce6c9da892573d115e8c826a73d400
TP_COMMIT=2f45015407c5c4baa5bbe30d7a37c2f82ec050a3
LIBS="brotli zlib bssl bcrypt expat libaio ip2loc libmaxminddb pcre2 udns libxml2"
AIO_VER=0.3.111
AIO_SHA512=440f2b62f99ca2e72ffc8c2c04b4779a1a7cf24a8ba2a30b34d18b4ee77630a2078610fe8c435559f81a5c3bfa93049bd53d77464a0da8267833fbde3f40ceeb

HERE=$(cd "$(dirname "$0")" && pwd)
PATCHES=$HERE/patches
WORK=${OLSCP_BUILD_DIR:-/root/olscp-build}
STAGE=${1:-all}
JOBS=$(nproc)

say() { echo "[$(date +%H:%M:%S)] $*"; }

deps() {
    dnf -y -q install gcc gcc-c++ make cmake git patch libtool autoconf automake golang libcap-devel \
        perl wget which >/dev/null
}

fetch() {
    mkdir -p "$WORK"
    cd "$WORK"
    if [ ! -d ols ]; then
        git clone -q --branch "$OLS_TAG" https://github.com/litespeedtech/openlitespeed.git ols
    fi
    git -C ols checkout -q -f "$OLS_COMMIT"
    git -C ols clean -qfdx -e build -e lsquic
    if [ ! -d third-party ]; then
        git clone -q https://github.com/litespeedtech/third-party.git
    fi
    git -C third-party checkout -q "$TP_COMMIT"
    cd ols
    local qc
    qc=$(cat LSQUICCOMMIT)
    if [ ! -f lsquic/.olscp-$qc ]; then
        rm -rf lsquic
        git clone -q https://github.com/litespeedtech/lsquic.git
        git -C lsquic checkout -q "$qc"
        git -C lsquic submodule -q update --init --recursive
        touch lsquic/.olscp-$qc
    fi
}

libs() {
    cd "$WORK/third-party"
    mkdir -p lib64 lib include
    if [ ! -f .olscp-submodules ]; then
        git submodule -q update --init
        touch .olscp-submodules
    fi
    cd script
    for l in $LIBS; do
        if [ -f "../.olscp-$l" ]; then continue; fi
        say "lib $l"
        if [ "$l" = libaio ]; then
            libaio > "$WORK/lib-$l.log" 2>&1 || { tail -30 "$WORK/lib-$l.log"; exit 1; }
        else
            ./build_$l.sh > "$WORK/lib-$l.log" 2>&1 || { tail -30 "$WORK/lib-$l.log"; exit 1; }
        fi
        touch "../.olscp-$l"
    done
}

libaio() {
    local prefix="$WORK/third-party" f=libaio-$AIO_VER.tar.gz
    cd "$prefix/src"
    rm -rf "libaio-$AIO_VER"
    curl -fsSLo "$f" "https://src.fedoraproject.org/repo/pkgs/rpms/libaio/$f/sha512/$AIO_SHA512/$f"
    echo "$AIO_SHA512  $f" | sha512sum -c
    tar xzf "$f"
    make -C "libaio-$AIO_VER" prefix="$prefix" install
    rm -f "$prefix"/lib/libaio.so*
    cd "$prefix/script"
}

prepare() {
    cd "$WORK/ols"
    for p in 'add_definitions(-DRUN_TEST)' 'add_definitions(-DPOOL_TESTING)' \
             'add_definitions(-DTEST_OUTPUT_PLAIN_CONF)' 'add_definitions(-DDEBUG_POOL)' \
             'set(libUnitTest' 'find_package(ZLIB' 'find_package(PCRE' 'add_subdirectory(test)' \
             'SET (CMAKE_C_COMPILER' 'SET (CMAKE_CXX_COMPILER'; do
        P="$p" perl -pi -e 's/^(\s*)(\Q$ENV{P}\E)/$1#$2/' CMakeLists.txt
    done
    sed -i -e 's/${unittest_STAT_SRCS}//g' -e 's/libstdc++.a//g' -e 's/-nodefaultlibs //g' src/CMakeLists.txt
    sed -i -e 's|^\(\s*\)ls_llmq.c|\1#ls_llmq.c|' -e 's|^\(\s*\)ls_llxq.c|\1#ls_llxq.c|' src/lsr/CMakeLists.txt
    for f in "$PATCHES"/*.patch; do
        [ -f "$f" ] || continue
        say "patch $(basename "$f")"
        patch -p1 --no-backup-if-mismatch < "$f"
    done
}

compile() {
    cd "$WORK/ols"
    mkdir -p build
    cd build
    rm -f CMakeCache.txt
    cmake -DCMAKE_BUILD_TYPE=RelWithDebInfo -DMOD_PAGESPEED=OFF -DMOD_SECURITY=OFF -DMOD_LUA=OFF .. > "$WORK/cmake.log" 2>&1 \
        || { tail -30 "$WORK/cmake.log"; exit 1; }
    make -j"$JOBS" openlitespeed > "$WORK/make.log" 2>&1 || { grep -m20 -B2 -A5 'error' "$WORK/make.log"; exit 1; }
    local out ver
    ver=$(cat "$HERE/../VERSION")
    out="$WORK/dist"
    mkdir -p "$out"
    strip -o "$out/openlitespeed" src/openlitespeed
    cd "$out"
    sha256sum openlitespeed > openlitespeed.sha256
    say "built $out/openlitespeed ($(./openlitespeed -v 2>&1 | head -1)) olscp $ver"
}

case "$STAGE" in
    deps) deps ;;
    fetch) fetch ;;
    libs) fetch; libs ;;
    build) fetch; prepare; compile ;;
    all) deps; fetch; libs; prepare; compile ;;
    *) echo "usage: $0 [all|deps|fetch|libs|build]"; exit 2 ;;
esac
