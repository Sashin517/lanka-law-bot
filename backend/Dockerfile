# ============================================================
# Stage 1: Builder — Install dependencies in a clean layer
# ============================================================
FROM python:3.12-slim AS builder

WORKDIR /build

# System dependencies for asyncpg, numpy, and sentence-transformers
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ============================================================
# Stage 2: Runtime — Minimal production image
# ============================================================
FROM python:3.12-slim AS runtime

WORKDIR /app

# Runtime-only system libs (libpq for asyncpg)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -r appuser && useradd -r -g appuser -d /app appuser

COPY --from=builder /install /usr/local

# Pre-bake models into Docker image to avoid cold-start latency on App Runner
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"
RUN python -c "from sentence_transformers import CrossEncoder; CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')"

# Copy application code
COPY main.py .
COPY alembic.ini .
COPY alembic/ alembic/
COPY app/ app/
COPY evaluation/ evaluation/
COPY database/ database/

# Create writable directories for runtime
RUN mkdir -p /app/storage/uploads /app/storage/processed_markdown \
    && chown -R appuser:appuser /app

USER appuser

# App Runner injects PORT env var (default 8080)
ENV PORT=8000
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

EXPOSE ${PORT}

# Health check for container orchestration
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:${PORT}/healthz || exit 1

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT} --workers 1 --timeout-keep-alive 75"]
