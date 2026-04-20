FROM python:3.12-slim AS base

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app

# Install dependencies first (cached layer)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# Copy application code
COPY app/ app/

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

# dev: includes Docker CLI so the backend can spawn ROMP sibling containers
# via the host socket (/var/run/docker.sock mounted in docker-compose.yml).
FROM docker:cli AS docker-cli

FROM base AS dev
COPY --from=docker-cli /usr/local/bin/docker /usr/local/bin/docker
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM base AS prod
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
