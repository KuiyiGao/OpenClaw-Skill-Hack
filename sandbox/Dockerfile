# Minimal base image: Python + the sandbox helper scripts (canary, egress proxy, entrypoint).
# Build: docker build -f sandbox/Dockerfile -t asshack-sandbox:latest .
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN groupadd -r lab && useradd -r -g lab -u 65532 -m -d /home/lab lab

WORKDIR /app
COPY sandbox/ ./sandbox/
RUN chmod +x ./sandbox/entrypoint.sh

USER 65532:65532
