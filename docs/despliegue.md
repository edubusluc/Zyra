# Despliegue con Docker

Zyra se despliega en **un solo servidor (VPS)** con Docker Compose. Esta página resume lo que hay en el
repositorio y cómo está montado el servidor (VPS Ubuntu, usuario `ubuntu`, app en `/opt/zyra`).

## Qué hay en el repositorio

| Fichero | Para qué sirve |
|---|---|
| `Dockerfile` | Dos imágenes con el mismo código: `web` (Python 3.11, dependencias con hash y estáticos; sin navegador) y `scheduler` (lo mismo más Chromium de Playwright, solo para el scraping de SNP). La base va fijada por digest. |
| `docker-compose.yml` | `db` (PostgreSQL 16), `web` (gunicorn), `scheduler` (`run_scheduler --loop`, imagen `zyra-scheduler`) y `caddy` (https y fotos). `postgres` y `caddy` van fijados por digest. |
| `Caddyfile` | Dominio, certificado automático, `/media/` y proxy hacia la web. Cambia el dominio si no es `zyrapadel.com`. |
| `deploy/deploy.sh` | Copia de seguridad, `check --deploy`, `migrate`, `createcachetable` y arranque; espera a que `/healthz/` responda. |
| `deploy/backup.sh` | Copia de la base de datos, las fotos y (cifrada) las claves; opcionalmente `rsync` fuera del servidor. Ver «Copias de seguridad». |
| `deploy/install-backup-cron.sh` | Programa la copia diaria (03:30) en el crontab del servidor. |
| `deploy/restore-test.sh` | Prueba de restauración en una base temporal, sin tocar la real. |
| `.github/workflows/deploy.yml` | En PR construye las dos imágenes y comprueba Chromium (lanzador) y la configuración (web); en `main` pasa los tests, publica las imágenes en GHCR y despliega por SSH solo si todo fue bien. |

El despliegue por SSH solo corre si la variable de repositorio `DEPLOY_ENABLED` vale `true`, y solo después de que pasen los tests y se publiquen las imágenes.
Si la huella del servidor cambia (reinstalación), actualiza `DEPLOY_KNOWN_HOSTS`: sin ella el despliegue se niega a conectar.
El secreto vale con la salida de `ssh-keyscan -t ed25519 IP_DEL_SERVIDOR` o solo con la línea `ssh-ed25519 AAAA…` (el despliegue le pone delante `DEPLOY_HOST`). Si el despliegue dice «No ED25519 host key is known», el secreto no tiene una clave ed25519 de ese servidor.

## Clave de despliegue (`DEPLOY_SSH_KEY`)

Si el despliegue dice `Permission denied (publickey,password)`, el servidor no reconoce la clave del secreto: su parte pública no está en `~/.ssh/authorized_keys` del usuario `ubuntu`.
Para crear una nueva (en PowerShell, una orden por línea):

1. `mkdir D:\CopiasZyra\claves` y `ssh-keygen -t ed25519 -N '""' -C "github-deploy" -f D:\CopiasZyra\claves\zyra_deploy`; comprueba que no tiene contraseña: `ssh-keygen -y -f D:\CopiasZyra\claves\zyra_deploy` no debe pedirla.
2. `type D:\CopiasZyra\claves\zyra_deploy.pub` muestra la clave pública (una línea `ssh-ed25519 AAAA…`).
3. En el servidor (`ssh ubuntu@IP`): `echo 'ssh-ed25519 AAAA… github-deploy' >> ~/.ssh/authorized_keys`
4. `type D:\CopiasZyra\claves\zyra_deploy` muestra la privada: pégala entera (con BEGIN y END) en el secreto `DEPLOY_SSH_KEY`. Si dice `error in libcrypto`, la clave se pegó cortada o tiene contraseña: usa mejor su base64 en una línea, `[Convert]::ToBase64String([IO.File]::ReadAllBytes("D:\CopiasZyra\claves\zyra_deploy"))`.
5. «Re-run failed jobs» en la ejecución fallida.

Para saber la pública de una privada que ya tienes: `ssh-keygen -y -f RUTA_DE_LA_PRIVADA`. Guarda la carpeta `claves` fuera del repositorio y en el gestor de contraseñas; la privada no se comparte.

## Montar el servidor desde cero

1. Instala Docker en el VPS, usa el usuario `ubuntu` (o crea otro y defínelo en el secreto `DEPLOY_USER`), desactiva el acceso por contraseña y abre solo los puertos 22, 80 y 443.
2. Crea el registro DNS `A` de `zyrapadel.com` hacia la IP del servidor (en Cloudflare, nube gris).
3. Copia a `/opt/zyra`: `docker-compose.yml`, `Caddyfile`, `deploy/deploy.sh` y `deploy/backup.sh`.
4. Crea `/opt/zyra/.env` a partir de `.env.example` (claves, dominios, `DATABASE_URL=postgres://zyra:CONTRASEÑA@db:5432/zyra`,
   `DJANGO_BEHIND_PROXY=True`, `DJANGO_TRUSTED_PROXY_COUNT=1`, correo y Google) y `db_password.txt` con la misma contraseña.
5. En el repositorio de GitHub: secretos `DEPLOY_SSH_KEY` (la llave privada, o su base64 en una línea con `base64 -w0 llave`), `DEPLOY_HOST` y `DEPLOY_KNOWN_HOSTS` (la huella del servidor: salida de `ssh-keyscan -t ed25519 IP_DEL_SERVIDOR`, que conviene comprobar contra `ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub` en el propio servidor), entorno `production` (con aprobación manual si quieres)
   y variable `DEPLOY_ENABLED=true`. Los paquetes de GHCR (`zyra` y `zyra-scheduler`) deben poder leerse desde el servidor (`docker login ghcr.io`).
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

- El CI construye dos imágenes por commit (`ghcr.io/edubusluc/zyra:sha-<commit>` y `ghcr.io/edubusluc/zyra-scheduler:sha-<commit>`) y las sube a GHCR.
- `deploy.sh` descarga la imagen, hace copia de seguridad, comprueba la configuración, aplica las migraciones y reinicia web y lanzador.
- Cuando la web queda sana, `deploy.sh` borra las imágenes antiguas salvo la versión nueva y la anterior (cada imagen pesa cientos de MB y sin limpiar el disco se llena). La versión anterior se conserva para poder volver atrás sin depender de GHCR.
- Las migraciones no se ejecutan al arrancar el contenedor, solo en `deploy.sh`, para que web y lanzador no choquen.
- Si la web no queda sana, el script lo dice y da el comando para volver a la versión anterior (`./deploy.sh <sha anterior>`).

## Volver atrás

Volver a la versión anterior del código **no deshace las migraciones**. Hay dos casos:

1. **La migración no cambió el esquema ni borró datos** (o no hubo migraciones): basta `cd /opt/zyra && ./deploy.sh $(cat .previous)`.
   La imagen anterior sigue en el servidor, no hace falta descargarla. Ojo: `deploy.sh` hace antes otra copia de seguridad.
2. **La migración cambió o borró datos** (o la versión nueva ha escrito datos que la anterior no entiende): hay que restaurar la copia que
   `deploy.sh` hizo justo antes de desplegar (la más reciente en `/opt/zyra/backups/` anterior al fallo; ver «Copias de seguridad» y
   `deploy/restore-test.sh`, que ensaya la restauración en una base temporal). Pasos: parar `web` y `scheduler`, restaurar la base (y las fotos si
   hace falta) desde esa copia, y lanzar `./deploy.sh $(cat .previous)`. Se pierde lo escrito entre la copia y la restauración.

La primera vez que se despliega tras separar las imágenes, la versión anterior era una sola imagen sin `zyra-scheduler`: volver a ella obliga a
arrancar el lanzador con la imagen `zyra` antigua (`ZYRA_SCHEDULER_IMAGE=ghcr.io/edubusluc/zyra:sha-<sha anterior> ./deploy.sh <sha anterior>`).

## Cargar los datos de partida en el servidor

La imagen web incluye `populate_db.py` y `populate/` (escudos); `clear_database.py` no va en la imagen y, aunque se copiara, se niega a borrar con `DJANGO_DEBUG=False`. Solo se carga si todavía no hay ningún club; las
cuentas que ya existan (por ejemplo tu superusuario) se conservan. En el servidor, en `/opt/zyra`:

```bash
export ZYRA_IMAGE=ghcr.io/edubusluc/zyra:sha-$(cat .current)
docker compose exec web python populate_db.py --usuario USUARIO_CAPITAN --email EMAIL_CAPITAN --sin-contrasena
```

Crea el club LOS GLADIADORES y una cuenta de capitán normal (`--superusuario` si además quieres que sea
staff). `--sin-contrasena` la deja entrar con Google (o tras `changepassword`). El usuario y el email deben
ser nuevos: el script se niega si ya existen.
