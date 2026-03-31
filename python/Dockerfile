# =============================================================================
# AIFred Trading Engine — Dockerfile
# Multi-stage build: compile TA-Lib C library in builder, copy into slim runtime
# =============================================================================

# ---------------------------------------------------------------------------
# Stage 1: Builder — compile TA-Lib C library and Python wheels
# ---------------------------------------------------------------------------
FROM python:3.11-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        wget \
        gcc \
        g++ \
        make \
    && rm -rf /var/lib/apt/lists/*

# Install TA-Lib C library from source
ARG TALIB_VERSION=0.4.0
RUN wget -q https://github.com/TA-Lib/ta-lib/releases/download/v${TALIB_VERSION}/ta-lib-${TALIB_VERSION}-src.tar.gz \
    && tar -xzf ta-lib-${TALIB_VERSION}-src.tar.gz \
    && cd ta-lib/ \
    && ./configure --prefix=/usr/local \
    && make -j"$(nproc)" \
    && make install \
    && cd .. \
    && rm -rf ta-lib ta-lib-${TALIB_VERSION}-src.tar.gz

# Install Python dependencies into a virtual env so we can copy it cleanly
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r /tmp/requirements.txt

# ---------------------------------------------------------------------------
# Stage 2: Runtime — slim image with only what we need
# ---------------------------------------------------------------------------
FROM python:3.11-slim AS runtime

# Install minimal runtime libraries needed by TA-Lib and other compiled deps
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgomp1 \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Copy TA-Lib shared libraries from builder
COPY --from=builder /usr/local/lib/libta_lib* /usr/local/lib/
RUN ldconfig

# Copy Python virtual env from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Set working directory
WORKDIR /app

# Copy source code
COPY src/ /app/src/

# Create persistent directories (will be overridden by volume mounts)
RUN mkdir -p /app/data /app/logs

# Ensure Python can resolve "src" as a package from /app
ENV PYTHONPATH="/app"

# Disable Python output buffering so logs appear in real time
ENV PYTHONUNBUFFERED=1

# Healthcheck: verify the main process is still running
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD pgrep -f "python -m src.main" > /dev/null || exit 1

# Run the trading engine
ENTRYPOINT ["python", "-m", "src.main"]

# Default to paper trading mode
CMD ["--mode", "paper"]
