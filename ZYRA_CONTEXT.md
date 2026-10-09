# ZYRA_CONTEXT · índice técnico

Punto de entrada para retomar cualquier tarea sin explorar todo el repositorio. Dirige la
investigación; no sustituye leer el código. Verificado contra `main` el 09/10/2026 (tras #103).
Leyenda: **[V]** comprobado en código o tests · **[I]** inferido · **[?]** pendiente de verificar.

## Qué es

Zyra es una web multi-club para capitanes de equipos de pádel de las Series Nacionales de Pádel
(SNP, snpgalaxy.com): plantilla, rivales, enfrentamientos, convocatorias, alineaciones, resultados,
informe PDF por email, estadísticas y un back-office para el dueño de la plataforma. Interfaz en
español con traducción al inglés.

## Stack confirmado [V]

- Python 3.11 (CI) · Django 5.1 · django-allauth (usuario/email + Google) · `requirements.txt`.
- SQLite en local, PostgreSQL 16 en producción (`DATABASE_URL`, `dj-database-url`).
- ReportLab (PDF), Pillow (fotos → WebP), Playwright/Chromium (scraper SNP), cryptography
  (Fernet), boto3 (Rekognition / S3 opcional), sentry-sdk, gunicorn.
- Front sin framework: plantillas Django + `static/style.css` + `static/js/*.js`.
- Docs: MkDocs Material + mkdocstrings (`mkdocs.yml`, `requirements-docs.txt`, hashes fijados).
- Sin servidor de colas: tareas en hilos y un lanzador `run_scheduler` llamado por cron.
- Hosting de producción: sin decidir. Netlify solo hace previews estáticas (`netlify.toml`).

## Arquitectura en una línea por pieza

- Configuración: `zyra/settings.py` (todo por entorno con `python-decouple`), URLs `zyra/urls.py`.
- Cada petición: `core.middleware.CurrentClubMiddleware` pone `request.club` / `request.membership`;
  las vistas usan `core.decorators.club_required` / `club_admin_required` (capitán).
- Apps: `core`, `players`, `team`, `match`, `call`, `callLog`, `penalty`, `data_analyse`, `backoffice`.
- Detalle de capas, dependencias y flujos: [docs/ai/architecture.md](docs/ai/architecture.md).

## Índice por funcionalidad

| Área | Archivos de entrada | Lógica principal | Datos relacionados | Tests | Documentación |
|---|---|---|---|---|---|
| Acceso, registro, Google, contraseñas | `core/urls.py`, `core/views.py` (`register_club`, `ThrottledLoginView`, `my_profile`) | `core/forms.py`, `core/adapters.py`, `core/services.py` (`create_club`) | `User`, `Club`, `Membership`, `Player.user` | `core/tests.py`, `core/tests_password.py`, `core/tests_profile.py`, `core/tests_security.py`, `players/test_own_player.py` | [business-rules § Cuentas](docs/ai/business-rules.md#cuentas-y-clubes) |
| Club, miembros, invitaciones, capitanes | `core/views.py` (`club_members`, `create_invitation*`, `invitation`, `leave_club`) | `core/services.py` (`accept_invitation`, `remove_membership`, `delete_club`), `core/emails.py`, `core/onboarding.py` | `Club`, `Membership`, `Invitation` | `core/tests_invitations.py`, `core/tests_delete_club.py`, `core/tests_onboarding.py` | [business-rules § Cuentas](docs/ai/business-rules.md#cuentas-y-clubes) |
| Jugadores y «Mi perfil» | `players/urls.py`, `players/views.py` | `players/forms.py`, `core/similarity.py`, `core/images.py` | `Player` | `players/tests.py`, `players/test_own_player.py`, `core/test_images.py` | [data-model § Player](docs/ai/data-model.md#player) |
| SNP: puntos y «Completar equipo» | `players/views.py` (`snp_account`, `complete_team_*`), comandos `update_snp_scores`, `complete_snp_team` | `players/scraper.py`, `players/snp.py`, `players/snp_import.py`, `core/crypto.py` | `SnpAccount`, `SnpScoreHistory`, `SnpTeamImport` | `players/tests.py` | [business-rules § SNP](docs/ai/business-rules.md#snp), `Readme.md` § Puntos SNP |
| Equipos (propio y rivales) | `team/urls.py`, `team/views.py` | `team/forms.py` (`Teamform.clean`), `core/similarity.py` | `Team` | `team/tests.py` | [business-rules § Equipos](docs/ai/business-rules.md#equipos) |
| Partidos (enfrentamientos, amistosos) | `match/urls.py`, `match/views.py` (`list_match`, `create_match`) | `match/forms.py` (`MatchForm`) | `Match` | `match/tests.py`, `match/tests_flow.py` | [business-rules § Partidos](docs/ai/business-rules.md#partidos-convocatorias-y-actas) |
| Convocatorias, registro y advertencias | `match/views.py` (`create_call`, `edit_call`, `close_call`), `call/views.py`, `callLog/views.py`, `penalty/views.py` | idem (sin capa de servicio) | `Call`, `CallLog`, `Penalty` | `match/tests.py`, `call/tests.py`, `callLog/tests.py`, `penalty/tests.py` | [business-rules § Partidos](docs/ai/business-rules.md#partidos-convocatorias-y-actas) |
| Alineación, resultados y cierre de acta | `match/views.py` (`create_game_for_match`, `create_result`, `close_match`, `suggested_lineup`) | `match/lineup.py`, `match/scoring.py`, `match/advisor.py` | `Game`, `Result` | `match/tests.py`, `match/tests_flow.py`, `match/tests_suggest.py` | [business-rules § Partidos](docs/ai/business-rules.md#partidos-convocatorias-y-actas) |
| Informe PDF y correo | `match/views.py` (`close_call`, `call_report_pdf`, `resend_call_report`), comando `send_call_reports` | `match/report.py`, `match/report_pdf.py`, `match/notifications.py`, `core/emails.py` | `ReportDelivery` | `match/tests_report.py` | [business-rules § Informe](docs/ai/business-rules.md#informe-pdf-y-correos) |
| Estadísticas | `data_analyse/urls.py`, `data_analyse/views.py` | `data_analyse/pairs.py`, `data_analyse/sets.py`, `data_analyse/records.py` | lee `Match`/`Game`/`Result`/`Call`/`Penalty` (sin modelos propios) | `data_analyse/tests.py`, `data_analyse/tests_extra.py` | [business-rules § Estadísticas](docs/ai/business-rules.md#estadísticas) |
| Back-office (staff) | `backoffice/urls.py`, `backoffice/views.py` | `backoffice/metrics.py`, `backoffice/sql.py`, `backoffice/importer.py`, `backoffice/middleware.py`, `backoffice/decorators.py` | `UserActivity`, `RequestMetric`, `SavedQuery`, `QueryLog`, `ImportJob` | `backoffice/tests.py` | `Readme.md` § Back-office |
| Procesos programados | `backoffice/jobs.py` (`JOBS`), comando `run_scheduler` | `backoffice/scheduler.py`, `backoffice/cron.py` | `ScheduledJob`, `JobRun` | `backoffice/tests.py` | [workflows § Procesos](docs/ai/workflows.md#procesos-programados) |
| Fotos y moderación | formularios con `clean_photo`, `backoffice/views.py` (`photo_*`) | `core/images.py`, `core/moderation.py`, `core/blocklist.py` | `PhotoCheck`, `PhotoRemoval`, `BlockedEmail` | `core/test_images.py`, `core/tests_blocklist.py` | [business-rules § Fotos](docs/ai/business-rules.md#fotos-moderación-y-bloqueos) |
| Idioma, SEO, legal, accesibilidad | `core/middleware.py` (`LanguageMiddleware`, `CanonicalHostMiddleware`), `core/views.py` (`legal_page`, `robots_txt`) | `core/seo.py`, `core/sitemaps.py`, `locale/en/LC_MESSAGES/` | — | `core/tests_i18n.py`, `core/tests_seo.py`, `core/tests_accessibility.py` | `docs/mantener-documentacion.md` § Accesibilidad |
| Identificadores públicos | `core/public_id.py` (`PublicIdModel`, conversor `<pid:...>`) | — | todos los modelos de dominio | `core/tests_public_id.py` | [decisions](docs/ai/decisions.md) |
| Datos de partida / reset | `clear_database.py`, `populate_db.py` | — | todas | no identificados | [workflows](docs/ai/workflows.md#base-de-datos) |

## Reglas críticas (no romper) [V]

1. Todo dato de dominio se filtra por `request.club`; nunca se busca un objeto solo por id
   (helpers `club_match`, `club_call` en `match/views.py`). Detalle en business-rules.
2. URLs con `public_id` (`<pid:...>`), nunca el `pk`. Modelo nuevo expuesto → `PublicIdModel` con prefijo propio.
3. Una cuenta pertenece a un solo club (`core.services.club_of`). Siempre queda al menos un capitán.
4. Convocatoria cerrable con ≥10 jugadores; partidos solo con convocatoria cerrada; acta con 5 partidos con resultado.
5. Acta cerrada (`Match.draft_mode=False`) = inmutable: no se borra el partido ni su convocatoria ni se editan parejas.
6. Resultados validados por `match/scoring.py`; `Game.save()` y `Result.save()` llaman a `clean()`.
7. Borrar un jugador conserva partidos (`SET_NULL` + `Game.removed_player_names`).
8. Cambio de modelo → migración en el mismo PR (CI: `makemigrations --check`).
9. Toda función/clase/módulo nuevo lleva docstring en español (CI: `scripts/check_docstrings.py`).
10. Textos visibles en español con `gettext`/`{% translate %}` + traducción en `locale/en/`.
11. Nunca secretos en código: todo por variables de entorno (`.env.example` las documenta).

## Comandos esenciales [V]

```bash
DJANGO_DEBUG=True python manage.py runserver
DJANGO_DEBUG=True python manage.py test --noinput
DJANGO_DEBUG=True python manage.py makemigrations --check --dry-run
python scripts/check_docstrings.py && mkdocs build --strict
```

Resto (migraciones de datos, scheduler, i18n, reset, despliegue): [docs/ai/workflows.md](docs/ai/workflows.md).

## Problemas conocidos vigentes

- [V] El freno de login (`core/views.py`, `ThrottledLoginView._key`) usa `REMOTE_ADDR`; detrás de un
  proxy todas las peticiones comparten IP. [I] Con la caché por defecto (no hay `CACHES`) el contador es por proceso.
- [V] Textos sin traducir guardados en BD: motivo de `Penalty` (`penalty/views.py`) y líneas de
  `CallLog` (`match/views.py`, `edit_call`).
- [V] Nombres `related_name` engañosos (`Call.match` → `match.match`, etc.): ver [data-model](docs/ai/data-model.md#trampas-de-related_name).
- [V] Partes de `Readme.md` § Multi-club están desfasadas (rol «Administrador», enlace de un solo uso,
  varios clubes por usuario). Manda el código; ver [decisions](docs/ai/decisions.md).

## Cómo abordar una tarea con el mínimo contexto

1. Lee este índice y localiza la fila del área afectada.
2. Abre solo el documento especializado enlazado (no todos):
   reglas → [business-rules](docs/ai/business-rules.md) · modelos → [data-model](docs/ai/data-model.md) ·
   capas/flujos → [architecture](docs/ai/architecture.md) · comandos → [workflows](docs/ai/workflows.md) ·
   «por qué está así» → [decisions](docs/ai/decisions.md).
3. Lee los archivos de entrada y lógica de la fila, y sus tests. Cada módulo tiene docstring: lee
   primero las de cabecera.
4. Amplía solo si un import o un FK te lleva fuera de la fila.
5. Para comportamiento visible al usuario, `docs/funcionalidades.md`; para historial, `docs/novedades.md`.

## Mantener este índice

- Va en el mismo PR que el cambio, junto con lo que ya pide `docs/mantener-documentacion.md`
  (docstrings, `docs/funcionalidades.md`, línea en `docs/novedades.md`).
- App, módulo o test nuevo → fila de la tabla. Regla nueva → `docs/ai/business-rules.md`.
  Modelo/FK/restricción → `docs/ai/data-model.md`. Comando o proceso → `docs/ai/workflows.md`.
  Cambio de enfoque → entrada en `docs/ai/decisions.md`.
- Solo rutas que existan; marca [I]/[?] lo no comprobado. Este archivo, por debajo de ~150 líneas.
- Para comprobar que las rutas citadas existen, usa el comando de
  [workflows § Validar la documentación](docs/ai/workflows.md#validar-la-documentación-para-ia).
