#!/usr/bin/env bash
# Prueba de restauración SIN tocar la base de datos real: carga la última copia en una base temporal
# (zyra_restore_test), compara el número de filas con la base real y la borra.
# Uso (en el servidor): ./restore-test.sh [copia.sql.gz[.enc]]   (por defecto, la más reciente)
set -euo pipefail
cd "$(dirname "$0")"
# shellcheck disable=SC1091
[ -f backup.env ] && . ./backup.env
PASS="${BACKUP_PASSPHRASE_FILE:-}"
FILE="${1:-$(ls -1t backups/zyra-*.sql.gz* 2>/dev/null | grep -v '\.part$' | head -1 || true)}"
[ -n "$FILE" ] && [ -f "$FILE" ] || { echo "No hay ninguna copia en backups/." >&2; exit 1; }
TMP_DB=zyra_restore_test
psql_admin() { docker compose exec -T db psql -U zyra -d postgres -v ON_ERROR_STOP=1 "$@"; }
trap 'psql_admin -qc "DROP DATABASE IF EXISTS $TMP_DB" >/dev/null 2>&1 || true' EXIT

psql_admin -qc "DROP DATABASE IF EXISTS $TMP_DB" -c "CREATE DATABASE $TMP_DB"
case "$FILE" in
  *.enc) [ -n "$PASS" ] || { echo "La copia está cifrada: define BACKUP_PASSPHRASE_FILE." >&2; exit 1; }
         openssl enc -d -aes-256-cbc -pbkdf2 -pass "file:$PASS" -in "$FILE" | gunzip ;;
  *)     gunzip -c "$FILE" ;;
esac | docker compose exec -T db psql -U zyra -d "$TMP_DB" -q -v ON_ERROR_STOP=1 > /dev/null

echo "Copia restaurada: $FILE"
printf '%-24s %12s %12s\n' tabla copia real
status=0
for table in auth_user core_club players_player match_match match_game call_call; do
  restored=$(docker compose exec -T db psql -U zyra -d "$TMP_DB" -Atc "SELECT count(*) FROM $table")
  live=$(docker compose exec -T db psql -U zyra -d zyra -Atc "SELECT count(*) FROM $table")
  printf '%-24s %12s %12s\n' "$table" "$restored" "$live"
  # La copia puede ir por detrás de la base real (se escribe a diario), pero nunca por delante ni vacía si la real no lo está.
  if [ "$restored" -gt "$live" ] || { [ "$restored" -eq 0 ] && [ "$live" -gt 0 ]; }; then status=1; fi
done
[ "$status" -eq 0 ] && echo "OK: la copia se restaura y sus datos son coherentes." || echo "ATENCIÓN: revisa las cifras de arriba." >&2
exit "$status"
