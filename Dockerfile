# ── SRE OpenEnv Dockerfile ────────────────────────────────────────────────────
FROM python:3.11-slim

# Metadata
LABEL name="sre-env" \
      version="1.0.0" \
      description="SRE Incident Response OpenEnv Environment" \
      org.openenv.tags="openenv,sre,devops"

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        && rm -rf /var/lib/apt/lists/*

# Create app user (HF Spaces requires non-root)
RUN useradd -m -u 1000 appuser

WORKDIR /app

# Install Python dependencies first (cache layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY --chown=appuser:appuser . .

# Switch to non-root user
USER appuser

# Environment
ENV PORT=7860 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    SERVER_URL=http://localhost:7860

EXPOSE 7860

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:7860/health || exit 1

# Start the combined FastAPI + Gradio server
CMD ["python", "main.py"]
