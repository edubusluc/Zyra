# Flujos de trabajo y comandos (para asistentes)

Solo comandos que existen en el repositorio (`Readme.md`, `.github/workflows/`, `docs/`,
`<app>/management/commands/`). Índice general: `ZYRA_CONTEXT.md`. Verificado el 09/10/2026.

## Entorno local

```bash
pip install -r requirements.txt
cp .env.example .env            # en local basta DJANGO_DEBUG=True
python manage.py migrate
python manage.py runserver
```

- Sin `DJANGO_DEBUG=True` la configuración arranca en modo producción y exige
  `DJANGO_SECRET_KEY` y `FIELD_ENCRYPTION_KEY` (`zyra/settings.py`).
- Sin `DATABASE_URL` usa SQLite (`db.sqlite3`). PostgreSQL local con Docker: `Readme.md` § PostgreSQL.
- Scraper SNP: además `playwright install chromium` (`Readme.md` § Puntos SNP).
- Sin `EMAIL_HOST_PASSWORD` los correos salen por consola.

## Tests y comprobaciones (lo mismo que el CI)

`.github/workflows/tests.yml` (SQLite y PostgreSQL 16, Python 3.11):

```bash
DJANGO_DEBUG=True python manage.py makemigrations --check --dry-run
DJANGO_DEBUG=True python manage.py test --noinput
DJANGO_DEBUG=True python manage.py test match.tests_flow     # una app o módulo concreto
```

Referencia: el 09/10/2026 la suite completa (519 tests) pasó en SQLite en unos 11 minutos;
mejor lanzar primero solo los tests del área tocada.

En PostgreSQL el CI corre además `python manage.py check --deploy --fail-level WARNING` con
`DJANGO_DEBUG=False` y claves generadas al vuelo (ver el workflow).

`.github/workflows/docs.yml`:

```bash
pip install --only-binary ':all:' --require-hashes -r requirements-docs.txt
python scripts/check_docstrings.py    # falla si falta un docstring (excluye migraciones y tests)
mkdocs build --strict                 # falla con enlaces rotos
mkdocs serve                          # vista local en http://127.0.0.1:8000
```

Tests por área: tabla de `ZYRA_CONTEXT.md`. No hay linter ni formateador configurado en el repositorio.

Accesibilidad con la web arrancada (Playwright + axe-core):
`python scripts/auditoria_accesibilidad.py --usuario <u> --contrasena '<p>' [--movil]`.

## Base de datos

- Cambio de modelo: `python manage.py makemigrations` y subir la migración en el mismo PR.
- Desplegar: `python manage.py migrate` (las migraciones están en git).
- Bases anteriores a las migraciones en git: `python manage.py adopt_repo_migrations [--dry-run]`.
- Empezar de cero (destructivo, pide confirmación): `python clear_database.py`
  (`--conservar-fotos` mantiene `media/`) y, opcional, `python populate_db.py` (club de pruebas
  LOS GLADIADORES; pide usuario, email y contraseña del capitán).
- SQLite → PostgreSQL vacío: `python manage.py copy_sqlite_to_db [ruta.sqlite3]`.
- Comandos de migraciones de datos antiguas: `assign_default_club`, `assign_public_ids`,
  `fill_match_locations`, `fix_duplicate_games [--dry-run]`, `move_photos_to_media`.

## Procesos programados

Definidos en `backoffice/jobs.py` (`JOBS`, horario cron en hora de Madrid). Un único lanzador
que el servidor debe ejecutar cada minuto:

```bash
python manage.py run_scheduler
```

| Proceso | Comando | Horario |
|---|---|---|
| `purge_request_metrics` | `purge_request_metrics` | 03:00 diario |
| `purge_job_runs` | `purge_job_runs` | 03:10 diario |
| `clear_sessions` | `clearsessions` (Django) | 03:30 diario |
| `update_snp_scores` | `update_snp_scores [--club X] [--all] [--batch-size N] [--headed]` | 23:00 diario |
| `send_call_reports` | `send_call_reports` | cada 5 min |
| `complete_snp_team` | `complete_snp_team <TEA...> [--dry-run]` | solo a mano |

Proceso nuevo: crear el comando de Django y añadir un `JobSpec` a `JOBS`; aparece en
*Back-office → Procesos*. Ejecutar a mano desde el back-office no espera al lanzador.

## Traducciones

Requiere `gettext` instalado:

```bash
python manage.py makemessages -l en -d django --no-obsolete -i "*/tests*.py"
python manage.py makemessages -l en -d djangojs --no-obsolete
python manage.py compilemessages -l en
```

Los `.po` y `.mo` de `locale/en/LC_MESSAGES/` están en git. Los msgid son el texto en español.

## Despliegue

- Hosting de producción sin decidir; no hay workflow de despliegue de la app. [V]
- Lista de variables y cómo generar claves: `.env.example`. Comprobación: `python manage.py check --deploy`.
- Pasos por versión (pip, `migrate`, comandos de relleno): secciones «Desplegar esta versión» de `Readme.md`.
- La web de documentación se publica sola en GitHub Pages en cada push a `main` (`.github/workflows/docs.yml`).
- Netlify: solo previews estáticas, no ejecuta Django (`netlify.toml`).

## Checklist de un PR

Según `docs/mantener-documentacion.md` y el CI:

1. Migración incluida si cambia un modelo.
2. Docstring en español en todo lo nuevo.
3. Textos nuevos traducidos (`makemessages` + `compilemessages`).
4. Página nueva → URL en `core/tests_accessibility.py`.
5. Comportamiento visible → `docs/funcionalidades.md`; línea en `docs/novedades.md` con el número del PR.
6. Afecta a la tabla, reglas, modelos o comandos → actualizar `ZYRA_CONTEXT.md` y el `docs/ai/*.md` correspondiente.

## Validar la documentación para IA

Comprueba que existen las rutas citadas entre comillas invertidas en el índice y en `docs/ai/`:

```bash
grep -ohE '`[A-Za-z_./-]+\.(py|md|html|yml|toml|txt|css|js)`' ZYRA_CONTEXT.md docs/ai/*.md \
  | tr -d '`' | sort -u | while read -r p; do [ -e "$p" ] || echo "NO EXISTE: $p"; done
```

Escribe siempre la ruta completa desde la raíz para que esta comprobación la cubra.
