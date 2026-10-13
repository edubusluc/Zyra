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
| `deploy/backup.sh` | `pg_dump` y copia de las fotos (14 días); opcionalmente `rsync` fuera del servidor. |
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

## Qué pasa en cada versión nueva

- El CI construye una imagen por commit (`ghcr.io/edubusluc/zyra:sha-<commit>`) y la sube a GHCR.
- `deploy.sh` descarga la imagen, hace copia de seguridad, comprueba la configuración, aplica las migraciones y reinicia web y lanzador.
- Las migraciones no se ejecutan al arrancar el contenedor, solo en `deploy.sh`, para que web y lanzador no choquen.
- Si la web no queda sana, el script lo dice y da el comando para volver a la versión anterior (`./deploy.sh <sha anterior>`).
  Las migraciones destructivas no se deshacen solas: para eso están las copias de `backups/`.

## Cargar los datos de partida en el servidor

La imagen incluye `populate_db.py` y `populate/` (escudos). Solo se usa sobre una base de datos sin clubes
ni usuarios (el script se niega si ya hay datos). En el servidor, en `/opt/zyra`:

```bash
export ZYRA_IMAGE=ghcr.io/edubusluc/zyra:sha-$(cat .current)
docker compose exec web python populate_db.py --usuario TU_USUARIO --email TU_EMAIL --sin-contrasena
```

`--sin-contrasena` deja al capitán entrar con Google (o tras `changepassword`). Si ya creaste un superusuario
con `createsuperuser`, bórralo antes (o cárgalo con ese mismo usuario tras eliminarlo) para que la base esté vacía.
