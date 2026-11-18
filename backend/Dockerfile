# FarmMarket API image. Build context is the REPO ROOT (see docker-compose.yml).
#
# Two stages:
#   1. node: builds the React frontend (frontend/ -> frontend/dist).
#   2. python: runs FastAPI and serves the built SPA from /frontend/dist
#      (app.main resolves <repo>/frontend/dist via Path(main.py).parents[2]).
#
# On container start, Alembic migrations run first (DATABASE_URL must point
# at a reachable database — compose wires it to the MySQL service), then
# uvicorn serves the API + SPA on $PORT (default 8000). Railway and Render
# inject PORT at runtime; the sh -c wrapper expands it at container start
# (an ENV line would bake the value in at build time instead — do NOT move
# the port into an ENV instruction).
FROM node:20-slim AS frontend-build
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
COPY backend/requirements.txt .
COPY backend/requirements-ortools.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir -r requirements-ortools.txt
# requirements-ortools.txt is installed in the image (unlike local dev, where
# it is opt-in) so POST /api/v1/logistics/optimize works in production
# instead of returning 503. No protobuf conflict: requirements.txt has no
# protobuf pin; the ortools/protobuf pins here are the tested combination.
COPY backend/ ./
COPY --from=frontend-build /build/dist /frontend/dist

# Run as a non-root user (dev and prod alike — this Dockerfile serves both).
# uvicorn binds $PORT (default 8000, >1024), so no privileges are needed.
# /app is owned by appuser so the uploads directory (created by app.main at
# startup under /app/uploads) stays writable. /frontend/dist is
# world-readable as-is.
RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app
USER appuser
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
