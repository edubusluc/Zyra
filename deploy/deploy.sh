#!/usr/bin/env bash
# Despliega una versión de la imagen: copia de seguridad, comprobaciones, migraciones y arranque.
# Uso (en el servidor): /opt/zyra/deploy.sh <sha-completo-del-commit>
set -euo pipefail
cd "$(dirname "$0")"
TAG="${1:?uso: deploy.sh <sha>}"
export ZYRA_IMAGE="ghcr.io/edubusluc/zyra:sha-${TAG#sha-}"
export ZYRA_SCHEDULER_IMAGE="${ZYRA_SCHEDULER_IMAGE:-ghcr.io/edubusluc/zyra-scheduler:sha-${TAG#sha-}}"

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
    # Cada despliegue deja imágenes nuevas (~800 MB): se borran las antiguas, pero se conserva la
    # versión anterior para poder volver atrás sin depender de GHCR (ver «Volver atrás» en docs/despliegue.md).
    keep="${TAG#sha-}|$(sed 's/^sha-//' .previous 2>/dev/null || true)"
    for repo in ghcr.io/edubusluc/zyra ghcr.io/edubusluc/zyra-scheduler; do
      docker images --format '{{.Tag}}' "$repo" | { grep -Ev "^sha-($keep)$" || true; } | while read -r old; do
        docker rmi "$repo:$old" > /dev/null 2>&1 || true
      done
    done
    docker image prune -f > /dev/null || echo "Aviso: no se pudieron borrar las imágenes sin etiqueta" >&2
    echo "OK: $TAG"
    exit 0
  fi
  sleep 2
done
echo "La web no está sana. Vuelve a la versión anterior con: ./deploy.sh $(cat .current 2>/dev/null || echo '<sha anterior>')" >&2
echo "(si la migración cambió datos, restaura antes la copia de justo antes del despliegue: docs/despliegue.md, «Volver atrás»)" >&2
exit 1
