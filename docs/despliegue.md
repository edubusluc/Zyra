# Despliegue con Docker

Zyra se despliega en **un solo servidor (VPS)** con Docker Compose. Esta página resume lo que ya hay en el
repositorio y los pasos que faltan cuando se compre el servidor.

## Qué hay en el repositorio

| Fichero | Para qué sirve |
|---|---|
| `Dockerfile` | Imagen única (Python 3.11, dependencias con hash, Chromium de Playwright y estáticos ya recopilados). La usan la web y el lanzador. |
| `docker-compose.yml` | `db` (PostgreSQL 16), `web` (gunicorn), `scheduler` (`run_scheduler --loop`) y `caddy` (https y fotos). |
| `Caddyfile` | Dominio, certificado automático, `/media/` y proxy hacia la web. Cambia el dominio si no es `zyrapadel.com`. |
| `deploy/deploy.sh` | Copia de seguridad, `check --deploy`, `migrate`, `createcachetable` y arranque; espera a que `/healthz/` responda. |
| `deploy/backup.sh` | Copia de la base de datos, las fotos y (cifrada) las claves; opcionalmente `rsync` fuera del servidor. Ver «Copias de seguridad». |
| `deploy/install-backup-cron.sh` | Programa la copia diaria (03:30) en el crontab del servidor. |
| `deploy/restore-test.sh` | Prueba de restauración en una base temporal, sin tocar la real. |
| `.github/workflows/deploy.yml` | En PR construye la imagen y comprueba Chromium y la configuración; en `main` la publica en GHCR. |

Mientras no exista el servidor no se rompe nada: el despliegue por SSH solo corre si la variable de
repositorio `DEPLOY_ENABLED` vale `true`.

## Cuando se compre el servidor

1. Instala Docker en el VPS, crea el usuario `zyra`, desactiva el acceso por contraseña y abre solo los puertos 22, 80 y 443.
2. Crea el registro DNS `A` de `zyrapadel.com` hacia la IP del servidor (en Cloudflare, nube gris).
3. Copia a `/opt/zyra`: `docker-compose.yml`, `Caddyfile`, `deploy/deploy.sh` y `deploy/backup.sh`.
4. Crea `/opt/zyra/.env` a partir de `.env.example` (claves, dominios, `DATABASE_URL=postgres://zyra:CONTRASEÑA@db:5432/zyra`,
   `DJANGO_BEHIND_PROXY=True`, `DJANGO_TRUSTED_PROXY_COUNT=1`, correo y Google) y `db_password.txt` con la misma contraseña.
5. En el repositorio de GitHub: secretos `DEPLOY_SSH_KEY` (la llave privada, o su base64 en una línea con `base64 -w0 llave`) y `DEPLOY_HOST`, entorno `production` (con aprobación manual si quieres)
   y variable `DEPLOY_ENABLED=true`. El paquete de GHCR debe poder leerse desde el servidor (`docker login ghcr.io`).
6. Primer arranque: `./deploy.sh <sha-completo-del-commit>` en el servidor, o un push a `main`.

## Copias de seguridad

`backup.sh` se ejecuta **antes de cada despliegue** (`deploy.sh`) y **cada día a las 03:30** (copia programada, `backup.sh daily`; sin argumentos equivale al modo despliegue y copia las fotos cada vez). Hace
`pg_dump` de la base de datos cada vez y copia de las fotos en cada despliegue y los domingos. Se conservan 14 días.
Una copia que está solo en el mismo servidor no sirve si el servidor se pierde: hay que enviarla fuera.

Configuración (una sola vez, en el servidor, en `/opt/zyra`):

1. Copia `deploy/backup.sh`, `deploy/install-backup-cron.sh` y `deploy/restore-test.sh` a `/opt/zyra` (a mano, como `deploy.sh`) y dales permiso de ejecución.
2. Crea `/opt/zyra/backup.pass` con una frase larga (`chmod 600`) y **guárdala también en tu gestor de contraseñas**: sin ella las copias cifradas no se abren.
3. Crea `/opt/zyra/backup.env`:

   ```bash
   BACKUP_PASSPHRASE_FILE=/opt/zyra/backup.pass      # cifra las copias (AES-256) e incluye .env y db_password.txt
   BACKUP_RSYNC_TARGET=usuario@otro-servidor:zyra/   # destino FUERA del servidor (rsync por SSH)
   BACKUP_KEEP_DAYS=14
   ```

4. Programa la copia diaria con el usuario dueño de `/opt/zyra` (en el servidor real, `zyra`; es quien despliega y puede leer `.env`): `sudo -u zyra ./install-backup-cron.sh`. Se puede repetir sin duplicar, sustituye una línea previa que llame a `backup.sh` (p. ej. una puesta a mano) y `--quitar` la retira. Los archivos de `/opt/zyra` (scripts, `backup.pass`, `backup.env`) deben ser de ese usuario: créalos con `sudo -u zyra`.
5. Comprueba que funciona: `./backup.sh daily` y `ls -l backups/`. `backups/.last-ok` guarda cuándo terminó la última copia correcta; `backups/backup.log`, la salida de la copia diaria.

**Las claves.** `FIELD_ENCRYPTION_KEY` (en `.env`) descifra las cuentas SNP guardadas: sin ella, una copia restaurada no las puede leer.
Con `BACKUP_PASSPHRASE_FILE` definido, cada copia incluye `claves-<fecha>.tgz.enc` con `.env` y `db_password.txt`; sin él no se
copian (irían sin cifrar). Guarda además `.env` en un sitio seguro aparte (gestor de contraseñas).

**Probar la restauración** (hazlo tras configurarlo y cada cierto tiempo): `./restore-test.sh` carga la última copia en una base
temporal, compara el número de filas de las tablas principales con la base real y la borra; no toca la base real. Para abrir una
copia cifrada a mano: `openssl enc -d -aes-256-cbc -pbkdf2 -pass file:backup.pass -in zyra-FECHA.sql.gz.enc | gunzip > zyra.sql`.

**Restaurar de verdad** (tras un desastre o una migración fallida): para `web` y `scheduler`, vacía la base y carga la copia en
`db` con `psql`, y vuelve a arrancar. Es una operación destructiva sobre los datos reales: hazla con calma y con una copia de lo que haya.

## Variables de seguridad del servidor

- **`EMAIL_HOST_PASSWORD`** (o un `EMAIL_BACKEND` real): obligatoria. Sin ella la aplicación no arranca en producción.
- **`SQL_CONSOLE_DATABASE_URL`**: sin ella la consola SQL del back-office no ejecuta consultas. Se crea el rol de solo lectura con
  `docker compose exec web python manage.py sql_readonly_role` (imprime el SQL; con `--apply` lo ejecuta, leyendo la contraseña de `SQL_CONSOLE_DB_PASSWORD`) y se pone en `.env` la URL
  del rol (`postgres://zyra_sql_readonly:CONTRASEÑA@db:5432/NOMBRE_BD`).
- **`FIELD_ENCRYPTION_KEY`**: para rotarla, pon la nueva delante de la antigua separadas por coma (`nueva,antigua`), reinicia,
  ejecuta `docker compose exec web python manage.py rotate_encryption_key` y, cuando diga que ha re-cifrado todo, quita la antigua.
- **`CSP_MODE`**: `report-only` (por defecto; los avisos salen en el log de `web` como «CSP violation»), luego `enforce`.
- **`DJANGO_SECURE_HSTS_SECONDS`**: un año por defecto.

## Qué pasa en cada versión nueva

- El CI construye una imagen por commit (`ghcr.io/edubusluc/zyra:sha-<commit>`) y la sube a GHCR.
- `deploy.sh` descarga la imagen, hace copia de seguridad, comprueba la configuración, aplica las migraciones y reinicia web y lanzador.
- Cuando la web queda sana, `deploy.sh` borra las imágenes que ya no usa ningún contenedor (`docker image prune -af`); sin esto el disco se llena (cada imagen pesa ~800 MB). Para volver atrás, el script vuelve a descargar la versión anterior de GHCR.
- Las migraciones no se ejecutan al arrancar el contenedor, solo en `deploy.sh`, para que web y lanzador no choquen.
- Si la web no queda sana, el script lo dice y da el comando para volver a la versión anterior (`./deploy.sh <sha anterior>`).
  Las migraciones destructivas no se deshacen solas: para eso están las copias de `backups/`.

## Cargar los datos de partida en el servidor

La imagen incluye `populate_db.py` y `populate/` (escudos). Solo se carga si todavía no hay ningún club; las
cuentas que ya existan (por ejemplo tu superusuario) se conservan. En el servidor, en `/opt/zyra`:

```bash
export ZYRA_IMAGE=ghcr.io/edubusluc/zyra:sha-$(cat .current)
docker compose exec web python populate_db.py --usuario USUARIO_CAPITAN --email EMAIL_CAPITAN --sin-contrasena
```

Crea el club LOS GLADIADORES y una cuenta de capitán normal (`--superusuario` si además quieres que sea
staff). `--sin-contrasena` la deja entrar con Google (o tras `changepassword`). El usuario y el email deben
ser nuevos: el script se niega si ya existen.
