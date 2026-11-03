# Helping Hands: one image with the FastAPI backend and the built React frontend (HH-19).
# Build:  docker build -t helping-hands .
# Run:    docker run -p 8000:8000 -e HH_SECRET_KEY=<long random value> helping-hands
#         then open http://localhost:8000 (API health: /api/v1/health)

# --- 1. Build the frontend ------------------------------------------------------------------
FROM node:20-alpine AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
# Same origin as the API, so the frontend calls relative /api URLs.
ENV VITE_API_BASE_URL=""
RUN npm run build

# --- 2. Backend runtime ---------------------------------------------------------------------
FROM python:3.12-slim
# Commit being built, reported by GET /api/v1/health (the deploy workflow passes it).
ARG HH_COMMIT=unknown
ENV HH_COMMIT=$HH_COMMIT \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HH_FRONTEND_DIST=/app/frontend \
    PORT=8000
WORKDIR /app

COPY backend/requirements.txt ./
RUN pip install -r requirements.txt

COPY backend/ ./
COPY --from=frontend /frontend/dist ./frontend
COPY deploy/start.sh ./start.sh

RUN useradd --create-home --uid 1000 hh && chmod +x start.sh && chown -R hh /app
USER hh

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/api/v1/health', timeout=4)"

CMD ["./start.sh"]
