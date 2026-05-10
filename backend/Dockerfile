FROM python:3.11-slim AS base

# Security: run as non-root user
RUN groupadd --gid 1001 mindai && \
    useradd --uid 1001 --gid mindai --shell /bin/bash --create-home mindai

WORKDIR /app

# Install system dependencies (minimal)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first (layer cache)
COPY pyproject.toml ./
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir ".[dev]"

# Copy application code
COPY . .

# Ensure correct ownership
RUN chown -R mindai:mindai /app

USER mindai

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
