# Backend Dockerfile
FROM python:3.11-slim

# System deps (optional: build tools for some libs)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements and install
COPY backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy backend source
COPY backend/ /app/

# Environment
ENV PYTHONUNBUFFERED=1 \
    UPLOAD_DIR=/tmp/uploads \
    DASHBOARD_DIR=/tmp/generated_dashboards \
    EXTERNAL_SCHEME=http

# Create temp dirs
RUN mkdir -p /tmp/uploads /tmp/generated_dashboards

# Expose API and Dash app ports (direct access to Dash apps on 8050-8060)
EXPOSE 8000 8050-8060

# Start FastAPI
CMD ["python", "start_backend.py"]
