#!/usr/bin/env bash
# Copia de la base de datos, de las fotos y (si se cifra) de las claves en /opt/zyra/backups.
#
# Uso:  ./backup.sh [deploy|daily]
#   deploy (por defecto)  antes de cada despliegue (lo llama deploy.sh): base de datos y fotos.
#   daily                 copia diaria programada (ver deploy/install-backup-cron.sh): base de datos cada día y
#                         fotos solo los domingos, para no llenar el disco.
#
# Configuración opcional en /opt/zyra/backup.env (se carga si existe; ver docs/despliegue.md):
#   BACKUP_RSYNC_TARGET=usuario@host:carpeta/   copia también FUERA del servidor (imprescindible)
#   BACKUP_PASSPHRASE_FILE=/opt/zyra/backup.pass   cifra las copias (AES-256) y añade el .env y db_password.txt
#   BACKUP_KEEP_DAYS=14                          días que se conservan
# Sin BACKUP_PASSPHRASE_FILE las copias van sin cifrar y NO se incluyen las claves (.env).
set -euo pipefail
cd "$(dirname "$0")"
MODE="${1:-deploy}"
case "$MODE" in deploy|daily) ;; *) echo "uso: backup.sh [deploy|daily]" >&2; exit 2 ;; esac
# shellcheck disable=SC1091
[ -f backup.env ] && . ./backup.env
KEEP_DAYS="${BACKUP_KEEP_DAYS:-14}"
PASS="${BACKUP_PASSPHRASE_FILE:-}"
if [ -n "$PASS" ] && [ ! -s "$PASS" ]; then
  echo "BACKUP_PASSPHRASE_FILE ($PASS) no existe o está vacío: no se hace la copia." >&2
  exit 1
fi

umask 077   # las copias llevan emails y hashes: solo las lee el propietario
mkdir -p backups
STAMP=$(date +%F-%H%M)

# Cifra de la entrada estándar a la salida estándar si hay frase de paso; si no, pasa los datos tal cual.
maybe_encrypt() {
  if [ -n "$PASS" ]; then openssl enc -aes-256-cbc -pbkdf2 -salt -pass "file:$PASS"; else cat; fi
}
EXT=""; [ -n "$PASS" ] && EXT=".enc"

# Se escribe en un fichero temporal y se renombra al terminar: una copia a medias nunca parece válida.
DUMP="backups/zyra-$STAMP.sql.gz$EXT"
docker compose exec -T db pg_dump -U zyra zyra | gzip | maybe_encrypt > "$DUMP.part"
mv "$DUMP.part" "$DUMP"

# Fotos: en cada despliegue y, en la copia diaria, solo los domingos.
# Si el volumen aún no existe no se crea aquí: lo crearía root y la web no podría escribir fotos.
if [ "$MODE" = deploy ] || [ "$(date +%u)" = 7 ]; then
  if docker volume inspect zyra_media > /dev/null 2>&1; then
    MEDIA="backups/media-$STAMP.tgz$EXT"
    docker run --rm -v zyra_media:/m:ro alpine tar czf - -C /m . | maybe_encrypt > "$MEDIA.part"
    mv "$MEDIA.part" "$MEDIA"
  fi
fi

# Las claves (sin FIELD_ENCRYPTION_KEY las cuentas SNP de una copia no se pueden leer) solo van cifradas.
if [ -n "$PASS" ]; then
  KEYS="backups/claves-$STAMP.tgz.enc"
  FILES=(); for f in .env db_password.txt; do [ -f "$f" ] && FILES+=("$f"); done
  if [ "${#FILES[@]}" -gt 0 ]; then
    tar czf - "${FILES[@]}" | maybe_encrypt > "$KEYS.part"
    mv "$KEYS.part" "$KEYS"
  fi
else
  echo "Aviso: copia sin cifrar. El .env no se incluye; guárdalo aparte (ver docs/despliegue.md)." >&2
fi

find backups -type f -mtime +"$KEEP_DAYS" -delete
if [ -n "${BACKUP_RSYNC_TARGET:-}" ]; then
  rsync -a backups/ "$BACKUP_RSYNC_TARGET"
else
  echo "Aviso: BACKUP_RSYNC_TARGET no está definido: las copias solo están en este servidor." >&2
fi
date -u +%FT%TZ > backups/.last-ok   # para vigilar que la copia diaria sigue funcionando
echo "OK: copia $MODE $STAMP"
