# syntax=docker/dockerfile:1

FROM python:3.12-slim AS base

RUN pip install --no-cache-dir uv

WORKDIR /app

# Copy dependency manifests first so this layer is cached until they change.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY app ./app

# Installs the project itself (a no-op given [tool.uv] package = false, but keeps
# the venv consistent if that ever changes) without re-resolving dependencies.
RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:${PATH}"

# Data directory for the SQLite-backed risk state, so it can be mounted as a
# volume and survive container restarts/recreations.
RUN mkdir -p /app/data
ENV DB_PATH=/app/data/tide_trader_state.db

# Must be 0.0.0.0 inside the container - Docker's port publishing is what
# controls host-network exposure, not the app's own bind address. Keep the
# published port bound to 127.0.0.1 on the host (see docker-compose.yml) to
# preserve the "local machine only" security posture this API relies on.
ENV HOST=0.0.0.0
ENV PORT=8000

EXPOSE 8000

CMD ["python", "-m", "app.main"]
