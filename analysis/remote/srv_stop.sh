#!/bin/sh
# Stop the server and confirm the port is free.
# Usage: srv_stop.sh <port> <pid>
# Prints "PORT_FREE" on success or "STILL_UP" on failure.

PORT="$1"
PID="$2"

kill "$PID" 2>/dev/null
i=0
while [ "$i" -lt 10 ]; do
    ss -ltn 2>/dev/null | grep -q ":$PORT " || break
    sleep 0.2
    i=$((i + 1))
done

kill -9 "$PID" 2>/dev/null
pkill -9 -x server 2>/dev/null

i=0
while [ "$i" -lt 25 ]; do
    ss -ltn 2>/dev/null | grep -q ":$PORT " || break
    sleep 0.2
    i=$((i + 1))
done

if ss -ltn 2>/dev/null | grep -q ":$PORT "; then
    echo "STILL_UP"
    exit 1
fi
echo "PORT_FREE"
