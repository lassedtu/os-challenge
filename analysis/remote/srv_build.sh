#!/bin/sh
# Rebuild the server with a fixed worker count.
# Usage: srv_build.sh <common_dir> <worker_count> [extra_cppflags...]

COMMON="$1"
WORKERS="$2"
shift 2
EXTRA="$*"

cd "$COMMON" || exit 1
make clean >/dev/null 2>&1
make CPPFLAGS="-D_DEFAULT_SOURCE -DWORKER_COUNT=$WORKERS $EXTRA" >/dev/null 2>/tmp/build.err
status=$?
if [ "$status" -ne 0 ]; then
    echo "BUILD_FAILED"
    cat /tmp/build.err
    exit 1
fi
echo "BUILD_OK"
