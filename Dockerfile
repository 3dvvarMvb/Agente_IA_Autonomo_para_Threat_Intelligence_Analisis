# ==============================================================================
# Stage 1: Build Environment & Dependencies
# ==============================================================================
FROM python:3.11-slim AS builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install python packaging tools
RUN pip install --no-cache-dir --upgrade pip setuptools wheel hatchling

# Copy project manifest and install dependencies
COPY pyproject.toml README.md /build/
COPY src/ /build/src/

# Build wheels
RUN pip wheel --no-cache-dir --no-deps --wheel-dir /build/wheels .

# ==============================================================================
# Stage 2: Hardened Minimal Production Runtime
# ==============================================================================
FROM python:3.11-slim AS runtime

# Security: prevent root execution
RUN groupadd -g 10001 appgroup && \
    useradd -u 10001 -g appgroup -s /bin/bash -m appuser

WORKDIR /app

# Install curl for healthchecks
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy wheel and dependencies from builder
COPY --from=builder /build/wheels /wheels
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir /wheels/*.whl && \
    rm -rf /wheels

# Copy knowledge base and recorded offline fixtures
COPY knowledge_base /app/knowledge_base
COPY fixtures /app/fixtures
COPY pyproject.toml /app/pyproject.toml

# Create persistent directories with correct permissions
RUN mkdir -p /app/data/chroma /app/.cache/diskcache && \
    chown -R appuser:appgroup /app

USER appuser

# Environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TI_AGENT_CACHE_DIR=/app/.cache/diskcache \
    TI_AGENT_CHROMA_PERSIST_DIR=/app/data/chroma

# Container healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD ti-agent version || exit 1

ENTRYPOINT ["ti-agent"]
CMD ["--help"]
