# 基础镜像：本框架（asshack）+ canary collector。仅用于离线/隔离实验。
# 构建上下文 = 仓库根：  docker build -f sandbox/Dockerfile -t asshack-sandbox:latest .
FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/src

# 非 root 用户（与 distroless nonroot 约定一致：uid 65532）
RUN groupadd -r lab && useradd -r -g lab -u 65532 -m -d /home/lab lab

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# 只拷贝运行所需，不含任何主机密钥
COPY src ./src
COPY scripts ./scripts
COPY data ./data
COPY configs ./configs
COPY sandbox ./sandbox

USER 65532:65532
# 默认：跑离线攻防 demo（无需任何网络）
CMD ["python", "scripts/run_demo.py"]
