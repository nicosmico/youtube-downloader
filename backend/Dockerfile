# syntax=docker/dockerfile:1
# Build context is the repository root.
#   target "backend": Python + uv + dev tools (ruff, pytest); used for tests and CI.
#   target "app"    (default): backend + the built Angular app; what `docker compose up` runs.

FROM python:3.13-slim AS backend
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /usr/local/bin/uv
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
WORKDIR /srv/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-install-project
COPY backend/ ./
CMD ["pytest"]

FROM node:24-slim AS web
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
# angular.json writes to ../backend/app/static
RUN npm run build

FROM backend AS app
COPY --from=web /build/backend/app/static ./app/static
CMD ["python", "-m", "app"]
