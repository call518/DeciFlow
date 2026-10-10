FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.7.20 /uv /usr/local/bin/uv

WORKDIR /app
ENV UV_PROJECT_ENVIRONMENT=/opt/deciflow-venv \
    PYTHONUNBUFFERED=1
EXPOSE 4000
CMD ["sh", "-c", "uv sync --frozen --no-dev --no-install-project --no-cache && exec /opt/deciflow-venv/bin/uvicorn server:app --host 0.0.0.0 --port ${PORT:-4000} --timeout-graceful-shutdown 2"]
