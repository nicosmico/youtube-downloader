FROM python:3.13-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /srv
COPY pyproject.toml ./
RUN uv sync --no-install-project
COPY app ./app
ENV PATH="/srv/.venv/bin:$PATH"
CMD ["python", "-m", "app.main"]
