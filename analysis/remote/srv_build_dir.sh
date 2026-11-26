#!/bin/sh
# Rebuild the server in a given directory with the normal build flags.
# Usage: srv_build_dir.sh <build_dir>
# The directory must contain the Makefile and src/ of the server.
# Prints "BUILD_OK" on success or "BUILD_FAILED" on failure.

DIR="$1"

cd "$DIR" || exit 1
make clean >/dev/null 2>&1
make >/dev/null 2>/tmp/build.err
status=$?
if [ "$status" -ne 0 ]; then
    echo "BUILD_FAILED"
    cat /tmp/build.err
    exit 1
fi
echo "BUILD_OK"
