FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install deps
COPY backend/pyproject.toml backend/poetry.lock* /app/backend/
RUN pip install --no-cache-dir poetry \
 && cd backend \
 && poetry config virtualenvs.create false \
 && poetry install --no-interaction --no-ansi

# Copy app
COPY backend /app/backend

WORKDIR /app/backend

EXPOSE 8000

# Run migrations + start
CMD ["bash", "-lc", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
