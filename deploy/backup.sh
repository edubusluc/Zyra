#!/usr/bin/env bash
# Copia de la base de datos y de las fotos en /opt/zyra/backups (14 días). Se ejecuta antes de cada despliegue.
# Para tenerla también fuera del servidor, define BACKUP_RSYNC_TARGET (usuario@host:carpeta/).
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p backups
STAMP=$(date +%F-%H%M)
docker compose exec -T db pg_dump -U zyra zyra | gzip > "backups/zyra-$STAMP.sql.gz"
docker run --rm -v zyra_media:/m:ro -v "$PWD/backups":/b alpine tar czf "/b/media-$STAMP.tgz" -C /m .
find backups -type f -mtime +14 -delete
if [ -n "${BACKUP_RSYNC_TARGET:-}" ]; then
  rsync -a backups/ "$BACKUP_RSYNC_TARGET"
fi
