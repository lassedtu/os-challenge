#!/bin/sh
# Rebuild the server with a fixed number of master workers and a fixed group size.
# Usage: srv_build_split.sh <common_dir> <master_count> <group_size> [extra_cppflags...]
# The total number of threads is master_count * group_size.
# Prints "BUILD_OK" on success or "BUILD_FAILED" on failure.

COMMON="$1"
MASTERS="$2"
GROUP="$3"
shift 3
EXTRA="$*"
TOTAL=$((MASTERS * GROUP))

cd "$COMMON" || exit 1
make clean >/dev/null 2>&1
make CPPFLAGS="-D_DEFAULT_SOURCE -DMASTER_COUNT=$MASTERS -DWORKERS_TOTAL=$TOTAL $EXTRA" \
    >/dev/null 2>/tmp/build.err
status=$?
if [ "$status" -ne 0 ]; then
    echo "BUILD_FAILED"
    cat /tmp/build.err
    exit 1
fi
echo "BUILD_OK"
