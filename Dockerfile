# syntax=docker/dockerfile:1.7

FROM python:3.11-slim AS python-builder

ENV POETRY_VERSION=1.8.3 \
    POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=true \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir "poetry==${POETRY_VERSION}"

COPY pyproject.toml README.md ./
RUN poetry install --only main --no-root --no-ansi

COPY src ./src
RUN poetry install --only main --no-ansi


FROM python:3.11-slim AS python-runtime

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SENTINEL_CONFIG=/app/config.yaml

WORKDIR /app

RUN useradd --create-home --shell /usr/sbin/nologin appuser \
    && mkdir -p /app/data /app/logs \
    && chown -R appuser:appuser /app

COPY --from=python-builder /app/.venv /app/.venv
COPY config.yaml main.py ./

USER appuser

VOLUME ["/app/data", "/app/logs"]
EXPOSE 8000

CMD ["macro-sentinel", "--config", "/app/config.yaml", "--loop"]


FROM node:20-alpine AS frontend-builder

WORKDIR /frontend

COPY frontend/package*.json ./
RUN npm install --no-audit --no-fund

COPY frontend ./
RUN npm run build


FROM nginx:1.27-alpine AS ui-runtime

COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=frontend-builder /frontend/dist /usr/share/nginx/html

EXPOSE 80
