# Arquitectura (para asistentes)

Referencia compacta para ubicar código. Índice general: `ZYRA_CONTEXT.md` (raíz del repositorio).
Verificado contra `main` el 11/11/2026 (tras #345). [V] comprobado · [I] inferido.

## Capas

Proyecto Django monolítico con renderizado en servidor. No hay SPA; la única API REST es `/api/v1/` para la app iOS (ver [API](#api-de-la-app-ios-apiv1)); algunos endpoints
devuelven JSON para el JavaScript de la página (p. ej. `suggested_lineup`, `complete_team_status`,
`run_live`, `password_check`). [V]

| Capa | Dónde | Notas |
|---|---|---|
| Configuración | `zyra/settings.py`, `.env.example` | Todo por entorno (`python-decouple`). Sin `DJANGO_DEBUG=True`, exige `DJANGO_SECRET_KEY` (≥50) y `FIELD_ENCRYPTION_KEY` o no arranca (`ImproperlyConfigured`). [V] |
| URLs | `zyra/urls.py` → `<app>/urls.py` | Conversor `pid` registrado en `zyra/urls.py`. `delete_call` vive en `call/views.py` pero se enruta desde `match/urls.py`. [V] |
| Middleware | `zyra/settings.py` `MIDDLEWARE` | Propios: `core.middleware.CanonicalHostMiddleware`, `backoffice.middleware.ActivityMiddleware`, `backoffice.impersonation.ImpersonationMiddleware` («Entrar como»: edición permitida, 30 min, cada POST/PUT/PATCH/DELETE auditado como `impersonate.write` con el personal real; bloquea las acciones sensibles de `BLOCKED_PREFIXES` (cuenta, perfil, abandonar club, clave SNP); las ediciones propias del personal van por `backoffice/views_edit.py`), `core.middleware.LanguageMiddleware`, `core.middleware.CurrentClubMiddleware`. [V] |
| Control de acceso | `core/decorators.py`, `backoffice/decorators.py` | `club_required`, `club_admin_required` (403), `staff_required` (404 a no-staff), `superuser_required`. [V] |
| Vistas (funciones) | `<app>/views.py` | Excepto `ThrottledLoginView` (clase). Mucha lógica está en las vistas, sobre todo en `match/views.py` y `data_analyse/views.py`. [V] |
| Servicios / dominio | `core/services.py`, `match/lineup.py`, `match/scoring.py`, `match/advisor.py`, `match/notifications.py`, `players/snp.py`, `players/snp_import.py`, `data_analyse/{pairs,sets,records}.py`, `backoffice/{scheduler,metrics,sql,importer}.py` | Funciones de módulo; no hay clases de servicio. [V] |
| Formularios | `<app>/forms.py` | Validaciones de negocio relevantes en `clean()` (`Teamform`, `MatchForm`). [V] |
| Modelos | `<app>/models.py` | Ver [data-model.md](data-model.md). |
| Plantillas | `<app>/templates/`, base en `core/templates/base.html` | Errores en popup y éxitos en toast desde la plantilla base (`core/templates/includes/messages_popup.html`). [V] |
| Estáticos | `static/style.css`, `static/js/*.js`, `static/zyra/` (marca y fuentes del PDF) | JS sin framework ni build. [V] |
| Procesos | `<app>/management/commands/`, `backoffice/jobs.py` | Ver [workflows.md](workflows.md#procesos-programados). |

## API de la app iOS (`/api/v1/`) [V]

App `api/`, aparte de la web. Autenticación por token de dispositivo (`Authorization: Bearer zyra_…`), sin sesión
ni cookies. Toda vista hereda de `api.views_base.ApiView`, que es la única puerta: exime del CSRF, autentica, limita,
elige el idioma (`Accept-Language`) y devuelve los errores como `{"error": código, "detail": texto}`; `api/tests_routes.py`
falla si una ruta no la usa o si es pública (`public = True`) sin declararla.

- **Token**: `DeviceToken` guarda solo el SHA-256 (`api/tokens.py`); revocable, caduca a `API_TOKEN_TTL_DAYS` (90) y se renueva al usarlo;
  `last_used_at` se anota como mucho cada `API_TOKEN_TOUCH_SECONDS` (300): dentro de esa ventana una petición no escribe en la base de datos.
- **Límites** (`api/throttle.py`, caché `ratelimit` en memoria de cada proceso, hasta N veces el límite con N procesos): por token
  (`API_RATE_LIMIT_PER_MINUTE`), por IP en rutas públicas (`API_PUBLIC_LIMIT_PER_MINUTE`) y por IP con tokens inválidos
  (`API_AUTH_FAILURES_PER_MINUTE`, corta antes de consultar la base de datos). `/api/` está exento del freno general por IP
  (`FloodProtectionMiddleware`): las IP móviles se comparten.
- **Acceso**: `POST /api/v1/auth/login` (público; cuerpo `{"login", "password", "device_name"?}`, `login` = usuario o email como en la web) devuelve el token en claro una sola vez
  (201); `POST /api/v1/auth/logout` revoca el token usado. Los fallos de contraseña usan el mismo freno que el login web (`core/login_throttle.py`: 5 por IP y usuario,
  30 por cuenta, 15 min): los fallos de uno bloquean al otro. 401 `invalid_credentials` es idéntico para cuenta inexistente, contraseña mala y cuenta desactivada. No llama a `login()` de Django: no hay sesión.
- **Registro push** (`POST /api/v1/devices`, `DELETE /api/v1/devices`, `api/push.py`): guarda el token de APNs del dispositivo (hexadecimal, `environment` `production`/`sandbox`, `app_version`); alta idempotente (201 la primera vez, 200 después) y **sin envío todavía**
  (cuando lo haya irá a un proceso aparte, nunca en un hilo web). Revocar el token (logout incluido) retira el registro. Los campos del cuerpo se validan en `api/fields.py`.
- **Iniciar sesión con Apple** (`POST /api/v1/auth/apple`, `api/apple.py`, `api/apple_accounts.py`): público y **desactivado por defecto** (sin `APPLE_CLIENT_IDS` responde 404 `not_found`). Cuerpo
  `{"identity_token", "nonce", "first_name"?, "last_name"?, "device_name"?}`; `nonce` es el valor en claro cuyo SHA-256 la app pasó a Apple. Se verifica firma RS256 con las claves de Apple (JWKS en caché 1 h; solo se redescargan
  cada 5 min ante un `kid` desconocido, con 3 s de espera), `iss`, `aud` (uno de `APPLE_CLIENT_IDS`), `exp`, `nonce`, y cada token se acepta una sola vez. Cuenta: la ya enlazada (`AppleIdentity.subject`); si no, la del mismo email
  solo si Apple lo verificó y la cuenta lo tenía verificado (si no, 409 `apple_account_unconfirmed`, sin enlazar ni crear); si no existe, se crea sin contraseña con el email verificado. Email bloqueado, cuenta desactivada o Apple sin email verificado: no entra.
  Respuesta 201 igual que el login. Pendiente fuera de este hito: al borrar la cuenta, Apple exige revocar su token en Apple (hace falta la clave `.p8` del Developer Portal).
- **Continuar con Google** (`POST /api/v1/auth/google`, `api/google.py`, `api/google_accounts.py`): igual que Apple pero con el `id_token` que la app obtiene con el flujo OAuth nativo (`ASWebAuthenticationSession`, PKCE) y un cliente de tipo iOS;
  público y **desactivado por defecto** (sin `GOOGLE_IOS_CLIENT_IDS`, 404 `not_found`, independiente del `GOOGLE_CLIENT_ID` de la web). Cuerpo `{"id_token", "nonce", "device_name"?}`; `nonce` es el valor en claro que Google devuelve tal cual en el token
  (se compara con `hmac.compare_digest`; un nonce vacío nunca vale). Se verifica firma RS256 con las claves de Google (JWKS en caché 1 h, misma política que Apple), `iss` (`accounts.google.com` con o sin `https://`), `aud`, `exp` y `nonce`, y cada token se acepta una sola vez.
  Cuenta: la ya enlazada, que es un `allauth.SocialAccount` (`provider="google"`, `uid=sub`) **compartido con la web**, así que no hay modelo ni migración nuevos; si no, la del mismo email (Google lo verificó), **igual que la web** (`core.adapters.find_account_by_email` + `claim_account`: si la cuenta no tenía el email verificado,
  se anula su contraseña y se borran sus otros emails y conexiones); si no existe, se crea sin contraseña (`api.apple_accounts.create_user`). Nombre y apellidos salen del token. Respuesta 201 igual que el login.
- **Eliminar cuenta** (`POST /api/v1/account/delete`, `api/views_account.py`): reutiliza `core.services.delete_account` y `account_delete_blocker` (misma regla que la web: el capitán debe traspasar antes, el personal no puede). Cuerpo `{"confirm", "delete_player"?}`:
  `confirm` es la contraseña (o el nombre de usuario en cuentas sin contraseña, `account_delete_confirmed`). 409 `account_blocked` con el motivo, 403 `confirmation_failed`, 429 tras 5 intentos por hora y usuario (`DELETE_ACCOUNT_LIMIT`). Revoca todos los dispositivos y borra la cuenta en una transacción.
- **Credenciales y personal**: cambiar, fijar o restablecer la contraseña (señales de allauth, `api/signals.py`) revoca todos los dispositivos de la cuenta (`tokens.revoke_all`); «Cerrar sesión en todos los dispositivos» (Mi perfil) también. Los tokens de cuentas del
  personal (`is_staff`/`is_superuser`) duran 12 h como su sesión web (`STAFF_SESSION_AGE`) y no se renuevan por uso.
- **Puente app → web** (`POST /api/v1/auth/web-session`, `api/web_session.py`): devuelve una URL `/app/session/<ticket>/` de un solo uso y 60 s (`TICKET_TTL_SECONDS`).
  El canje (`api/views_web.py`, vista web, no JSON) crea la sesión web normal (`login()` + duración de «Mantener la sesión iniciada», 12 h si es del personal) y redirige a la ruta `next`
  sin el ticket en la URL ni en `Referer` (`Referrer-Policy: no-referrer`, sin caché). Solo se canjea con el User-Agent `ZyraApp/` (un navegador o una vista previa de enlaces ni lo gasta). Seguridad:
  ticket de 256 bits guardado como hash; gasto atómico (`UPDATE` condicional); vale solo mientras el token del dispositivo y la cuenta estén activos; `next` solo rutas relativas (sin `//`, dominios, esquemas ni `/api/`), validado al pedir el ticket;
  no se liga a la IP (la red móvil cambia). Revocar el token (`api.tokens.revoke_token`, logout incluido) cierra las sesiones web que abrió ese dispositivo. Límite por token: `API_WEB_SESSION_LIMIT_PER_MINUTE`.
- **Modo app en la web**: la app muestra páginas de la web (p. ej. tras `web-session`) con el User-Agent `ZyraApp/<versión>`;
  `core.context_processors.app_mode` pone `is_app` y `core/templates/base.html` quita la cabecera y el menú inferior (`<body class="z-app">`; el CSS del final de `static/style.css` no reserva su hueco). Solo cambia la presentación, no da permisos. Con cualquier otro User-Agent el HTML es idéntico (`core/tests_app_mode.py`).
  En modo app tampoco se ofrece «Entrar con Google» (`google_login` pone `google_login_enabled` a falso con `is_app`): Google bloquea su pantalla de acceso en una WebView.
- **Sin efectos en la web**: sin cookie no hay sesión ni consulta de membresías; `core.tests_safety_net` no recorre `api/`.

## Contexto de club por petición [V]

`CurrentClubMiddleware` (`core/middleware.py`) carga las membresías del usuario, descarta clubes
suspendidos, toma el club guardado en sesión (`club_id`) o el primero, y rellena `request.club`,
`request.membership`, `request.user_memberships` y `request.suspended_clubs`. Los context processors
de `core/context_processors.py` (`club`, `navigation`, `google_login`, `site`) lo exponen a las plantillas.

## Dependencias entre apps [V]

No hay capas estrictas entre apps: los imports son cruzados.

- `core` es la base (Club, Membership, public_id, imágenes, emails), pero `core/views.py`,
  `core/onboarding.py`, `core/season_prep.py` y `core/admin.py` importan `match`, `players`, `team` y `data_analyse`.
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
3. **Ciclo de un enfrentamiento** [V]: `create_match` (→ `edit_match_date`, solo con acta abierta; recalcula `season`) → `create_call` / `edit_call` (escribe
   `CallLog`) → `close_call` (≥10 jugadores) → `match.notifications.send_call_report` (PDF de
   `match/report.py` + `match/report_pdf.py`, cola `ReportDelivery`) → `create_game_for_match`
   (`match/lineup.py`; sugerencias con `match/advisor.py`) → `create_result` / `edit_result`
   (`match/scoring.py`) → `close_match` (calcula puntos y `Match.result`).
4. **Puntos SNP** [V]: `run_scheduler` lanza `update_snp_scores` (lunes, martes y miércoles 05:00 hora de Madrid,
   un ciclo por ejecución) → `players.snp.sync_club` → `players.scraper.scrape_scores` (Playwright) →
   `Player.snp_score` + `SnpScoreHistory`.
5. **Completar equipo** [V]: sin botón en Jugadores; lo lanza el alta del club con SNP, la tarea «Sincronizar datos» de la portada hasta que haya una búsqueda `done` (`snp_import.sync_task`: idle/running/ready/failed; «Reintentar» tras fallo o cancelación) (`start_search` despierta la cola al momento con `_wake_queue`; `complete_team_start` con `from=home`: confirma solo y lleva a `complete_team_welcome`) o el administrador desde el back-office. `complete_team_start` → `players.snp_import.start_search` (hilo en
   segundo plano; con el ajuste `SNP_IMPORT_INLINE` corre en línea, lo usan los tests) → `scrape_scores(with_group_teams=True)` (jugadores + equipos de la Clasificación) → la página consulta `complete_team_status` →
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
| AWS Rekognition | `core/moderation.py` | Desactivado a propósito (`REKOGNITION_ENABLED = False` fijo en settings); las fotos las revisa el personal |
| S3 compatible | `zyra/settings.py` `STORAGES` | `DJANGO_MEDIA_STORAGE` |
| Sentry | `zyra/settings.py` | `SENTRY_DSN` |

## Concurrencia y procesos en segundo plano [V]

No hay Celery ni colas. «Completar equipo», «Ejecutar ahora» del back-office y el latido de los
procesos usan `threading.Thread` dentro del proceso web o del comando (`players/snp_import.py`,
`backoffice/scheduler.py`). [I] Un reinicio del servidor corta esos hilos; el scheduler lo detecta
por falta de latido (10 min) y `snp_import` marca búsquedas viejas con `STALE_AFTER` (10 min).
