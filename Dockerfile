# syntax=docker/dockerfile:1.7

# --- Stage 1: build the frontend ---
FROM node:20-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci
COPY frontend/ ./
# Vite outDir is ../backend/static, so create that mountpoint
RUN mkdir -p /app/backend/static && npm run build


# --- Stage 2: backend runtime ---
FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/backend/.venv \
    PATH="/app/backend/.venv/bin:$PATH"

# OpenCV (headless) still needs libgl + glib for video decoding
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

WORKDIR /app/backend

# Install deps first for cacheability
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# App code
COPY backend/app ./app

# Built SPA from stage 1
COPY --from=frontend /app/backend/static ./static

EXPOSE 8000

CMD ["uv", "run", "--no-dev", "--frozen", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
