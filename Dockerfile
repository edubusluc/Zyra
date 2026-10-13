# syntax=docker/dockerfile:1
# Imagen única de Zyra: la usan la web (gunicorn) y el lanzador de procesos (run_scheduler).
FROM python:3.11-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

# 1) Dependencias: esta capa solo cambia si cambia requirements.txt.
COPY requirements.txt .
RUN pip install --no-cache-dir --only-binary :all: --require-hashes -r requirements.txt \
 && playwright install --with-deps chromium \
 && rm -rf /var/lib/apt/lists/*

# 2) Código y estáticos (se sirven con WhiteNoise, con el hash en el nombre).
COPY . .
RUN DJANGO_DEBUG=False DJANGO_SECRET_KEY=solo-para-collectstatic-sin-uso-real-0123456789abcdef \
    FIELD_ENCRYPTION_KEY=MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY= \
    ADMIN_URL=solo-para-collectstatic/ DJANGO_ALLOWED_HOSTS=localhost \
    python manage.py collectstatic --noinput

# 3) Usuario sin privilegios; media/ es un volumen que debe poder escribir.
RUN useradd --create-home zyra \
 && mkdir -p /app/media \
 && chown -R zyra: /app/media /ms-playwright
USER zyra

EXPOSE 8000
CMD ["gunicorn", "zyra.wsgi", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "60", "--access-logfile", "-"]
