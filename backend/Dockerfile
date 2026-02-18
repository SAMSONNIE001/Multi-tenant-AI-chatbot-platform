FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# System deps (kept minimal)
RUN pip install --no-cache-dir --upgrade pip

# Copy backend project
COPY pyproject.toml /app/pyproject.toml
COPY app /app/app

# Install dependencies (PEP 517/518 not needed here since we use simple deps)
RUN pip install --no-cache-dir -e .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
