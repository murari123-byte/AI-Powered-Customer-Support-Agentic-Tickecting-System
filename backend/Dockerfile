# Backend image: used by the API, the Celery worker and one-off commands (migrations, CLI).
FROM python:3.12-slim

# No .pyc files; print logs straight away (important for `docker compose logs`).
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dependencies first: this layer is cached and only rebuilt when requirements.txt changes.
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Never run as root inside the container.
RUN useradd --create-home --uid 1000 app && chown -R app /app
USER app

EXPOSE 8000
# Default: the API. The worker service in docker-compose.yml overrides this command.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
