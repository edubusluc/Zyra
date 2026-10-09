# Arquitectura (para asistentes)

Referencia compacta para ubicar código. Índice general: `ZYRA_CONTEXT.md` (raíz del repositorio).
Verificado contra `main` el 09/10/2026. [V] comprobado · [I] inferido.

## Capas

Proyecto Django monolítico con renderizado en servidor. No hay API REST ni SPA; algunos endpoints
devuelven JSON para el JavaScript de la página (p. ej. `suggested_lineup`, `complete_team_status`,
`run_live`, `password_check`). [V]

| Capa | Dónde | Notas |
|---|---|---|
| Configuración | `zyra/settings.py`, `.env.example` | Todo por entorno (`python-decouple`). Sin `DJANGO_DEBUG=True`, exige `DJANGO_SECRET_KEY` (≥50) y `FIELD_ENCRYPTION_KEY` o no arranca (`ImproperlyConfigured`). [V] |
| URLs | `zyra/urls.py` → `<app>/urls.py` | Conversor `pid` registrado en `zyra/urls.py`. `delete_call` vive en `call/views.py` pero se enruta desde `match/urls.py`. [V] |
| Middleware | `zyra/settings.py` `MIDDLEWARE` | Propios: `core.middleware.CanonicalHostMiddleware`, `backoffice.middleware.ActivityMiddleware`, `core.middleware.LanguageMiddleware`, `core.middleware.CurrentClubMiddleware`. [V] |
| Control de acceso | `core/decorators.py`, `backoffice/decorators.py` | `club_required`, `club_admin_required` (403), `staff_required` (404 a no-staff), `superuser_required`. [V] |
| Vistas (funciones) | `<app>/views.py` | Excepto `ThrottledLoginView` (clase). Mucha lógica está en las vistas, sobre todo en `match/views.py` y `data_analyse/views.py`. [V] |
| Servicios / dominio | `core/services.py`, `match/lineup.py`, `match/scoring.py`, `match/advisor.py`, `match/notifications.py`, `players/snp.py`, `players/snp_import.py`, `data_analyse/{pairs,sets,records}.py`, `backoffice/{scheduler,metrics,sql,importer}.py` | Funciones de módulo; no hay clases de servicio. [V] |
| Formularios | `<app>/forms.py` | Validaciones de negocio relevantes en `clean()` (`Teamform`, `MatchForm`). [V] |
| Modelos | `<app>/models.py` | Ver [data-model.md](data-model.md). |
| Plantillas | `<app>/templates/`, base en `core/templates/base.html` | Errores en popup y éxitos en toast desde la plantilla base (`core/templates/includes/messages_popup.html`). [V] |
| Estáticos | `static/style.css`, `static/js/*.js`, `static/zyra/` (marca y fuentes del PDF) | JS sin framework ni build. [V] |
| Procesos | `<app>/management/commands/`, `backoffice/jobs.py` | Ver [workflows.md](workflows.md#procesos-programados). |

## Contexto de club por petición [V]

`CurrentClubMiddleware` (`core/middleware.py`) carga las membresías del usuario, descarta clubes
suspendidos, toma el club guardado en sesión (`club_id`) o el primero, y rellena `request.club`,
`request.membership`, `request.user_memberships` y `request.suspended_clubs`. Los context processors
de `core/context_processors.py` (`club`, `navigation`, `google_login`, `site`) lo exponen a las plantillas.

## Dependencias entre apps [V]

No hay capas estrictas entre apps: los imports son cruzados.

- `core` es la base (Club, Membership, public_id, imágenes, emails), pero `core/views.py`,
  `core/onboarding.py` y `core/admin.py` importan `match`, `players`, `team` y `data_analyse`.
- `players` → `core`, `team`; su comando `update_snp_scores` importa `backoffice.cron` y `backoffice.jobs`.
- `match` → `core`, `team`, `players`, `call`, `callLog`, `penalty`, `data_analyse`.
- `data_analyse` → solo lee modelos de otras apps; no tiene modelos propios.
- `backoffice` → lee todos los modelos; sus procesos ejecutan comandos de otras apps.

Cuidado con imports circulares: `match.models` importa `players.models`; `players.models` importa
`team.models` y `core.models`. Algunas funciones importan dentro del cuerpo para evitarlo
(p. ej. `core.services.remove_membership`). [V]

## Flujos principales

1. **Alta de club** [V]: `core.views.register_club` → `core.services.create_club` crea `Club`,
   `Team(is_own=True, in_group=True)`, `Membership(role=admin)` y, si se da nombre, el `Player`
   del capitán enlazado a su cuenta. Si se registra con cuenta SNP, lanza `players.snp_import.start_search(..., auto_confirm=True)` y
   redirige a `players.views.complete_team_welcome`.
2. **Invitación** [V]: `create_invitation` (email, un uso) o `create_invitation_link` (enlace
   compartido `reusable`) → `core.views.invitation` → `core.services.accept_invitation`
   (transacción con `select_for_update`). El nuevo miembro elige su jugador en `players.views.my_player` / `link_player`.
3. **Ciclo de un enfrentamiento** [V]: `create_match` → `create_call` / `edit_call` (escribe
   `CallLog`) → `close_call` (≥10 jugadores) → `match.notifications.send_call_report` (PDF de
   `match/report.py` + `match/report_pdf.py`, cola `ReportDelivery`) → `create_game_for_match`
   (`match/lineup.py`; sugerencias con `match/advisor.py`) → `create_result` / `edit_result`
   (`match/scoring.py`) → `close_match` (calcula puntos y `Match.result`).
4. **Puntos SNP** [V]: `run_scheduler` lanza `update_snp_scores` (diario 23:00 hora de Madrid,
   ciclo semanal) → `players.snp.sync_club` → `players.scraper.scrape_scores` (Playwright) →
   `Player.snp_score` + `SnpScoreHistory`.
5. **Completar equipo** [V]: `complete_team_start` → `players.snp_import.start_search` (hilo en
   segundo plano; con el ajuste `SNP_IMPORT_INLINE` corre en línea, lo usan los tests) → la página consulta `complete_team_status` →
   `complete_team_confirm` → `snp_import.confirm`.
6. **Estadísticas** [V]: `data_analyse.views.*` construyen un log de partidos cerrados
   (`pairs.club_game_log`, `build_game_log`) y calculan en Python; filtros por temporada y tipo de
   partido vía querystring (`?season=`, `?match_type=`, `?player=`, `?p1=&p2=`).

## Integraciones externas [V]

| Servicio | Código | Activación |
|---|---|---|
| SNP (snpgalaxy.com) | `players/scraper.py` | `SnpAccount` del club (credenciales cifradas con `core/crypto.py`) |
| SMTP (Gmail por defecto) | `core/emails.py`, `match/notifications.py` | `EMAIL_HOST_PASSWORD`; sin ella, backend de consola |
| Google OAuth | `core/adapters.py`, allauth | `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` |
| AWS Rekognition | `core/moderation.py` | `REKOGNITION_ENABLED` + claves (desactivado por defecto) |
| S3 compatible | `zyra/settings.py` `STORAGES` | `DJANGO_MEDIA_STORAGE` |
| Sentry | `zyra/settings.py` | `SENTRY_DSN` |

## Concurrencia y procesos en segundo plano [V]

No hay Celery ni colas. «Completar equipo», «Ejecutar ahora» del back-office y el latido de los
procesos usan `threading.Thread` dentro del proceso web o del comando (`players/snp_import.py`,
`backoffice/scheduler.py`). [I] Un reinicio del servidor corta esos hilos; el scheduler lo detecta
por falta de latido (10 min) y `snp_import` marca búsquedas viejas con `STALE_AFTER` (10 min).
