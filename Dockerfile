# ==============================================================================
# Multi-stage Dockerfile for Sydon (Returns Manager)
# Unified deployment: Vite React SPA + FastAPI Python Backend
# ==============================================================================

# Stage 1: Build Frontend UI
FROM node:20-slim AS frontend-builder
WORKDIR /app/ui

# Install dependencies
COPY ui/package.json ui/package-lock.json* ./
RUN npm ci || npm install

# Build static bundle
COPY ui/ ./
RUN npm run build

# Stage 2: Python Backend & Server
FROM python:3.12-slim AS runner
WORKDIR /app

# System dependencies for OpenCV, Pillow, PyMuPDF, and psycopg
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgl1 \
    libglib2.0-0 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies from agent/pyproject.toml
COPY agent/pyproject.toml agent/README.md /app/agent/
RUN pip install --no-cache-dir -e /app/agent

# Copy backend source, reference definitions and contract schemas
COPY agent/ /app/agent/
COPY reference/ /app/reference/
COPY contract/ /app/contract/

# Copy built frontend from Stage 1 into ui/dist
COPY --from=frontend-builder /app/ui/dist /app/ui/dist

# Expose port (Render sets $PORT dynamically, defaults to 10000)
ENV PYTHONUNBUFFERED=1 \
    PORT=10000 \
    RM_ENV=demo \
    PYTHONPATH=/app/agent/src

EXPOSE 10000

# Start unified web service using uvicorn factory
CMD ["sh", "-c", "uvicorn returns_manager.api.app:create_app --factory --host 0.0.0.0 --port ${PORT:-10000}"]
