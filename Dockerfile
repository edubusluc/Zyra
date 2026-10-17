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
COPY manage.py ./
COPY zyra ./zyra
COPY locale ./locale
COPY static ./static
COPY backoffice ./backoffice
COPY call ./call
COPY callLog ./callLog
COPY core ./core
COPY data_analyse ./data_analyse
COPY match ./match
COPY penalty ./penalty
COPY players ./players
COPY team ./team
# Datos de partida (se cargan a mano con `python populate_db.py`, ver docs/despliegue.md).
COPY populate ./populate
COPY populate_db.py ./
# Claves desechables generadas aquí mismo: collectstatic las exige pero no las usa, y no quedan en la imagen.
RUN DJANGO_DEBUG=False \
    DJANGO_SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(64))')" \
    FIELD_ENCRYPTION_KEY="$(python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')" \
    ADMIN_URL=solo-para-collectstatic/ DJANGO_ALLOWED_HOSTS=localhost \
    python manage.py collectstatic --noinput

# 3) Usuario sin privilegios; media/ es un volumen que debe poder escribir.
RUN useradd --create-home zyra \
 && mkdir -p /app/media \
 && chown -R zyra: /app/media /ms-playwright
USER zyra

EXPOSE 8000
CMD ["gunicorn", "zyra.wsgi", "--bind", "0.0.0.0:8000", "--workers", "3", "--worker-class", "gthread", "--threads", "4", "--timeout", "60", "--graceful-timeout", "30", "--max-requests", "1000", "--max-requests-jitter", "100", "--limit-request-line", "4094", "--access-logfile", "-"]
