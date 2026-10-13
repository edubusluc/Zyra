#!/usr/bin/env bash
# Despliega una versión de la imagen: copia de seguridad, comprobaciones, migraciones y arranque.
# Uso (en el servidor): /opt/zyra/deploy.sh <sha-completo-del-commit>
set -euo pipefail
cd "$(dirname "$0")"
TAG="${1:?uso: deploy.sh <sha>}"
export ZYRA_IMAGE="ghcr.io/edubusluc/zyra:sha-${TAG#sha-}"

docker compose pull web scheduler
docker compose up -d --wait db                  # espera a que PostgreSQL esté sano
./backup.sh                                        # copia ANTES de tocar nada
docker compose run --rm web python manage.py check --deploy --fail-level ERROR
docker compose run --rm web python manage.py migrate --noinput
docker compose run --rm web python manage.py createcachetable
docker compose up -d web scheduler caddy
for _ in $(seq 1 30); do
  if [ "$(docker inspect -f '{{.State.Health.Status}}' zyra-web-1)" = healthy ]; then
    [ -f .current ] && cp .current .previous
    echo "$TAG" > .current
    echo "OK: $TAG"
    exit 0
  fi
  sleep 2
done
echo "La web no está sana. Vuelve a la versión anterior con: ./deploy.sh $(cat .previous 2>/dev/null || echo '<sha anterior>')" >&2
exit 1
