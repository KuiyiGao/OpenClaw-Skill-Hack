#!/bin/sh
# Default entrypoint: run egress-proxy (8080) and canary (8088) in parallel.
# The container exits when either dies — docker-compose can restart it.
set -e
( python -m firewall.runtime.canary ) &
CANARY_PID=$!
( python -m firewall.runtime.egress_proxy ) &
PROXY_PID=$!
trap 'kill -TERM $CANARY_PID $PROXY_PID 2>/dev/null' INT TERM
wait -n
exit $?
