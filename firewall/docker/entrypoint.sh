#!/usr/bin/env bash
# Default entrypoint: run egress-proxy (8080) and canary (8088) in parallel.
# `wait -n` requires bash, not dash. The image must have bash installed.
set -e
( python -m firewall.runtime.canary ) &
CANARY_PID=$!
( python -m firewall.runtime.egress_proxy ) &
PROXY_PID=$!
trap 'kill -TERM $CANARY_PID $PROXY_PID 2>/dev/null' INT TERM
# If either child dies, exit so docker compose can restart us.
wait -n
exit $?
