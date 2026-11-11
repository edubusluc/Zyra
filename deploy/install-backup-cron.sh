#!/usr/bin/env bash
# Programa la copia diaria (backup.sh daily) a las 03:30 en el crontab del usuario que lo ejecuta.
# Ejecútalo con el usuario dueño de /opt/zyra, que es quien también despliega: sudo -u zyra ./install-backup-cron.sh
# Si ese usuario ya tenía una línea que llama a backup.sh, la sustituye en vez de duplicarla; se puede repetir
# sin duplicar. Para quitarla: ./install-backup-cron.sh --quitar
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
TAG="# zyra-backup-diario"
LINE="30 3 * * * cd $DIR && ./backup.sh daily >> $DIR/backups/backup.log 2>&1 $TAG"
mkdir -p "$DIR/backups"
CURRENT="$(crontab -l 2>/dev/null || true)"
# Se quitan la línea de este script y cualquier otra que llame a backup.sh (p. ej. una puesta a mano).
REPLACED="$(printf '%s\n' "$CURRENT" | grep -E 'backup\.sh' || true)"
CLEAN="$(printf '%s\n' "$CURRENT" | grep -v -E 'backup\.sh' || true)"
if [ "${1:-}" = "--quitar" ]; then
  printf '%s\n' "$CLEAN" | crontab -
  echo "Copia diaria quitada."
  exit 0
fi
{ [ -n "$CLEAN" ] && printf '%s\n' "$CLEAN"; printf '%s\n' "$LINE"; } | crontab -
[ -n "$REPLACED" ] && printf 'Sustituida la línea anterior:\n%s\n' "$REPLACED"
echo "Copia diaria programada a las 03:30: $LINE"
