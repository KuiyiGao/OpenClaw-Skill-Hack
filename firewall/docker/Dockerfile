# Minimal firewall image — egress proxy + canary + the python package.
# Users who want a sandboxed agent (e.g. OpenClaw) layer that on top of
# this image and route their traffic through HTTP_PROXY=http://proxy:8080.

FROM python:3.11-slim

# bash is needed by entrypoint.sh (wait -n is bash-only, not dash).
RUN apt-get update -y \
 && apt-get install -y --no-install-recommends bash \
 && rm -rf /var/lib/apt/lists/* \
 && useradd -u 65532 -m -s /usr/sbin/nologin firewall
WORKDIR /firewall
COPY pyproject.toml /firewall/
COPY firewall /firewall/firewall
RUN pip install --no-cache-dir .

# State dir mount point; pre-created so the non-root user can write events.
RUN mkdir -p /firewall/.state && chown -R 65532:65532 /firewall/.state /firewall
USER 65532:65532
ENV PYTHONUNBUFFERED=1
EXPOSE 8080 8088

# Default: bring up both egress-proxy and canary in the same process tree.
ENTRYPOINT ["/firewall/firewall/docker/entrypoint.sh"]
