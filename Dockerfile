# ──────────────────────────────────────────────────────────────────────────────
# WCP Widget: Claude Analytics
# Multi-stage build — keeps the final image small and secure.
# ──────────────────────────────────────────────────────────────────────────────

FROM python:3.12-slim AS base

WORKDIR /app

# Install dependencies first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY src/ ./src/
COPY agents/ ./agents/

# Create data directory (will be mounted as a volume in production)
RUN mkdir -p /app/data

# Environment
ENV CONTAINER_NAME=wcp-widget-claude
ENV FLASK_APP=src/app.py
ENV PYTHONUNBUFFERED=1

EXPOSE 3746

# Run as non-root for security
RUN useradd -r -s /bin/false appuser && chown -R appuser:appuser /app
USER appuser

CMD ["python", "src/app.py"]
