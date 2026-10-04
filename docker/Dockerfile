# ============================================================
# Telegram Channel Management Suite - production image
# Same codebase as local/portable (decision D-004).
# Multi-stage: build the SPA with Node, then run without Node.
# Never bake secrets or session files into the image.
# ============================================================

# --- Stage 1: build the frontend ---
FROM node:20-alpine AS frontend
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# --- Stage 2: runtime ---
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install dependencies first for better layer caching.
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# Application code.
COPY backend/ ./backend/

# Versioned database migrations (applied at startup; guarded by a backup).
COPY alembic.ini ./alembic.ini
COPY migrations/ ./migrations/

# Built SPA from stage 1.
COPY --from=frontend /src/backend/app/static/ ./backend/app/static/

# Runtime data directories (populated via volumes at run time).
RUN mkdir -p data sessions backups logs exports

EXPOSE 8000

# Run as a non-root user.
RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app
USER appuser

CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
