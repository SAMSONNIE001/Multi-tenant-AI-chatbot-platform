FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Root directory is /backend, so copy from current context
COPY pyproject.toml poetry.lock* /app/backend/

RUN pip install --no-cache-dir poetry \
 && cd /app/backend \
 && poetry config virtualenvs.create false \
 && poetry install --no-interaction --no-ansi --no-root \
 && pip install --no-cache-dir "bcrypt<4.1" \
 && pip install --no-cache-dir python-multipart

COPY . /app/backend

WORKDIR /app/backend

EXPOSE 8000

CMD ["bash", "-lc", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
