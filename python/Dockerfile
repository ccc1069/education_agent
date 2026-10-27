# ============================================================
# 多Agent智能教育系统 - Python/FastAPI 后端
# 多阶段构建: builder(编译依赖) + runtime(精简运行时)
# ============================================================

# ---- builder ----
FROM python:3.11-slim AS builder

WORKDIR /app

# 系统依赖(asyncpg 需要 libpq, cryptography 需要 build-essential)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ---- runtime ----
FROM python:3.11-slim

WORKDIR /app

# 仅运行时依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -r -u 1000 -d /app -s /sbin/nologin appuser

# 从 builder 拷贝已安装的依赖
COPY --from=builder /install /usr/local
COPY --chown=appuser:appuser . /app

USER appuser

# 元数据
LABEL org.opencontainers.image.title="multi-agent-education-python" \
      org.opencontainers.image.description="Multi-Agent Intelligent Education System - Python/FastAPI Backend" \
      org.opencontainers.image.version="2.0.0" \
      org.opencontainers.image.source="https://github.com/example/multi-agent-education"

EXPOSE 8000

# 健康检查(K8s probe 之外,容器运行时层兜底)
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

# 生产启动: gunicorn + uvicorn worker (多进程 + 异步)
# workers = 2 * CPU核 + 1, 此处默认 4 可通过 GUNICORN_WORKERS 覆盖
ENV GUNICORN_WORKERS=4
ENV GUNICORN_BIND=0.0.0.0:8000
ENV GUNICORN_TIMEOUT=120
ENV GUNICORN_KEEPALIVE=5
ENV GUNICORN_MAX_REQUESTS=10000
ENV GUNICORN_MAX_REQUESTS_JITTER=1000

CMD exec gunicorn api.main:app \
    -w ${GUNICORN_WORKERS} \
    -k uvicorn.workers.UvicornWorker \
    -b ${GUNICORN_BIND} \
    --timeout ${GUNICORN_TIMEOUT} \
    --keep-alive ${GUNICORN_KEEPALIVE} \
    --max-requests ${GUNICORN_MAX_REQUESTS} \
    --max-requests-jitter ${GUNICORN_MAX_REQUESTS_JITTER} \
    --access-logfile - \
    --error-logfile - \
    --log-level info \
    --graceful-timeout 30
