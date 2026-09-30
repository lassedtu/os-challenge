#!/bin/sh
# Run the client once against the server.
# Usage: run_client.sh <client_bin> <server_ip> <port> <seed> <total> <start> \
#                       <difficulty> <rep> <delay> <lambda>

exec "$1" "$2" "$3" "$4" "$5" "$6" "$7" "$8" "$9" "${10}" "${11}"
