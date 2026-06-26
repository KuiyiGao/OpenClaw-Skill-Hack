#!/usr/bin/env bash
# Default entrypoint: run egress-proxy (8080) and canary (8088) in parallel.
# `wait -n` requires bash, not dash. The image must have bash installed.
set -e
# Bind all interfaces INSIDE the container so the compose network (openclaw ->
# firewall:8080) and the host port mapping (127.0.0.1:8080->8080) can reach us.
# The container is network-isolated; only mapped host ports are exposed.
export FIREWALL_BIND="${FIREWALL_BIND:-0.0.0.0}"
( python -m firewall.runtime.canary ) &
CANARY_PID=$!
( python -m firewall.runtime.egress_proxy ) &
PROXY_PID=$!
trap 'kill -TERM $CANARY_PID $PROXY_PID 2>/dev/null' INT TERM
# If either child dies, exit so docker compose can restart us.
wait -n
exit $?
