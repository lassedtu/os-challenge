#!/bin/sh
# Start the server fully detached and wait until it listens.
# Usage: srv_start.sh <common_dir> <port>
# Prints "PID=<n>" and "LISTENING" on success; "NOT_LISTENING" on failure.

COMMON="$1"
PORT="$2"

pkill -9 -x server 2>/dev/null
i=0
while [ "$i" -lt 25 ]; do
    ss -ltn 2>/dev/null | grep -q ":$PORT " || break
    sleep 0.2
    i=$((i + 1))
done

cd "$COMMON" || exit 1
setsid ./server "$PORT" </dev/null >/tmp/server.log 2>&1 &
echo "PID=$!"

i=0
while [ "$i" -lt 25 ]; do
    if ss -ltn 2>/dev/null | grep -q ":$PORT "; then
        echo "LISTENING"
        exit 0
    fi
    sleep 0.2
    i=$((i + 1))
done
echo "NOT_LISTENING"
cat /tmp/server.log 2>/dev/null
exit 1
