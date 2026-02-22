# Multi-stage: build frontend, then run backend serving it + API

# ---- Frontend build ----
FROM node:20-alpine AS frontend-build
WORKDIR /app/frontend

COPY frontend/package.json frontend/package-lock.json* ./
# Install all deps including devDependencies (vite) for the build
RUN npm ci 2>/dev/null || npm install
COPY frontend/ ./
# Same-origin API when served from backend
ENV VITE_API_URL=
RUN npm run build

# ---- Backend + serve frontend ----
FROM python:3.12-slim AS backend
WORKDIR /app

# Minimal system deps (curl for healthcheck; add tesseract-ocr if you need image invoice OCR)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Backend code and project config (README.md required by pyproject.toml)
COPY pyproject.toml README.md ./
COPY backend/ ./backend/
RUN mkdir -p data

# Install backend and dependencies (from pyproject.toml)
RUN pip install --no-cache-dir .

# Copy built frontend into static dir for FastAPI to serve
COPY --from=frontend-build /app/frontend/dist ./static

ENV PYTHONUNBUFFERED=1
ENV SERVE_FRONTEND=1
EXPOSE 8000

# Default: run API only (use docker-compose to add poller if needed)
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
