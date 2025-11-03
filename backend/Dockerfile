FROM python:3.11-slim

ARG PIP_INDEX_URL
ARG PIP_EXTRA_INDEX_URL

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH="/app"

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends libpq5 curl && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /tmp/requirements.txt
RUN pip install --upgrade pip && \
    if [ -n "$PIP_INDEX_URL" ]; then \
        pip config set global.index-url "$PIP_INDEX_URL"; \
    fi && \
    if [ -n "$PIP_EXTRA_INDEX_URL" ]; then \
        pip config set global.extra-index-url "$PIP_EXTRA_INDEX_URL"; \
    fi && \
    pip install --no-cache-dir --prefer-binary -r /tmp/requirements.txt

COPY . /app

EXPOSE 8000

CMD ["sh", "-c", "sh ./scripts/import_check.sh && alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers ${UVICORN_WORKERS:-2}"]
