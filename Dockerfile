# ==============================================================================
# Dockerfile — Tigo LATAM Competitive Radar (Google Cloud Run Jobs Ready)
# ==============================================================================
FROM mcr.microsoft.com/playwright/python:v1.49.1-noble

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PLAYWRIGHT_HEADLESS=true

WORKDIR /app

# Install pinned Python dependencies first for optimal Docker layer caching
COPY requirements.txt /app/requirements.txt
RUN pip install --upgrade pip && \
    pip install -r /app/requirements.txt

# Copy repository source and 12-market catalog configuration
COPY config/ /app/config/
COPY src/ /app/src/
COPY tests/ /app/tests/
COPY main.py /app/main.py

# Pre-create non-root writable data directories for Cloud Run volume / GCS FUSE mounts
RUN mkdir -p /app/data/audit_trail /app/data/reports && \
    chown -R pwuser:pwuser /app

USER pwuser

ENTRYPOINT ["python", "main.py"]
