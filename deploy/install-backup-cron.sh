#!/usr/bin/env bash
# Programa la copia diaria (backup.sh daily) a las 03:30 en el crontab del usuario que lo ejecuta.
# Se puede repetir sin duplicar la línea. Uso (en el servidor, con el usuario que despliega): ./install-backup-cron.sh
# Para quitarla: ./install-backup-cron.sh --quitar
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
TAG="# zyra-backup-diario"
LINE="30 3 * * * cd $DIR && ./backup.sh daily >> $DIR/backups/backup.log 2>&1 $TAG"
mkdir -p "$DIR/backups"
CURRENT="$(crontab -l 2>/dev/null || true)"
CLEAN="$(printf '%s\n' "$CURRENT" | grep -v -F "$TAG" || true)"
if [ "${1:-}" = "--quitar" ]; then
  printf '%s\n' "$CLEAN" | crontab -
  echo "Copia diaria quitada."
  exit 0
fi
{ [ -n "$CLEAN" ] && printf '%s\n' "$CLEAN"; printf '%s\n' "$LINE"; } | crontab -
echo "Copia diaria programada a las 03:30: $LINE"
