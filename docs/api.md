# API de la app iOS (`/api/v1/`)

Contrato de la API que usa la app de Zyra. Es independiente de la web: no usa sesión ni cookies y cada petición
va autenticada con un **token de dispositivo**. El código está en `api/`; las reglas internas, en
[arquitectura](ai/architecture.md#api-de-la-app-ios-apiv1).

## Convenciones

- **Base**: `https://<SITE_URL>/api/v1/`. Usa siempre el dominio de `SITE_URL`: en otro la web redirige con un 301 y un `POST` se rompe.
  La barra final es opcional (`/auth/login` y `/auth/login/` valen).
- **Formato**: cuerpos y respuestas en JSON (`Content-Type: application/json`). Todas las respuestas llevan `Cache-Control: no-store`.
- **Autenticación**: `Authorization: Bearer zyra_…` en todo salvo en las rutas marcadas como públicas.
- **Idioma**: `Accept-Language: es` o `en` para el texto de `detail`. El cliente debe apoyarse en `error`, que es estable y no se traduce.
- **Errores**: siempre `{"error": "<código>", "detail": "<texto para personas>"}` con el estado HTTP que corresponda, también en 404 y 405.
- **Cuentas del personal de Zyra** (`is_staff`): su token dura 12 h y no se renueva, como su sesión web.

## Token de dispositivo

- Se obtiene con `/auth/login` o `/auth/apple` y se devuelve **una sola vez**: el servidor solo guarda su hash. Si se pierde, se inicia sesión de nuevo.
- Dura 90 días (`API_TOKEN_TTL_DAYS`) y se renueva con el uso. Una cuenta que no abra la app en ese tiempo tendrá que entrar otra vez.
- Se revoca con `/auth/logout` (solo ese dispositivo), al cambiar o restablecer la contraseña (todos los de la cuenta), con
  «Cerrar sesión en todos los dispositivos» de Mi perfil y al eliminar la cuenta. Un token caducado, revocado o inexistente da el mismo `401 unauthorized`.
- Guárdalo en el Llavero de iOS, no en `UserDefaults`.

## Endpoints

| Método y ruta | Público | Para qué |
|---|---|---|
| `GET /home` | no | Datos del Inicio nativo: situación de la cuenta, equipos y rol en cada uno |
| `GET /matches/<id>` | no | Ficha de un enfrentamiento del equipo de la cuenta: estado, fases, convocados, parejas, respuesta del jugador y acción principal de quien gestiona |
| `GET /ping` | no | Comprueba que el token sirve, cuándo caduca y a qué equipo pertenece |
| `POST /auth/login` | sí | Usuario o email y contraseña → token |
| `POST /auth/register` | sí | Cuenta de jugador sin club (email y contraseña; el usuario es opcional) → token |
| `POST /auth/apple` | sí | `identity_token` de Apple → token (desactivado hasta configurarlo) |
| `POST /auth/google` | sí | `id_token` de Google → token (desactivado hasta configurarlo) |
| `GET /club/options` | sí | Competiciones, divisiones, países y categorías del alta de club |
| `POST /club/register` | sí | Crea cuenta (o usa Google) y club en una llamada → token |
| `POST /auth/logout` | no | Revoca el token usado |
| `POST /auth/web-session` | no | URL de un solo uso para abrir la web ya con la sesión iniciada |
| `POST /devices` | no | Registra o actualiza el token de APNs de este dispositivo |
| `DELETE /devices` | no | Retira el registro push |
| `POST /account/delete` | no | Elimina la cuenta |

### `GET /ping`

```json
{"device": "DVTxxxxxxxxxxxx", "expires_at": "2027-02-16T21:10:00+00:00", "team": {"name": "Club A", "crest": null}, "has_history": true}
```

`team` es el equipo propio del primer club de la cuenta, o `null` si no está en ninguno. `has_history` es verdadero si la cuenta tiene fichas, actuales o de equipos anteriores (la app ofrece entonces «Mis estadísticas» a quien no tiene equipo). La app lo comprueba al volver a primer plano para saber si salió de su equipo (o entró en uno) desde la web.

### `GET /home`

Base del Inicio nativo. Las tarjetas (próximo enfrentamiento, pendientes, «Mi forma», avisos) se añadirán a esta respuesta en las siguientes fases.

```json
{
  "state": "ok",
  "user": {"username": "ana", "display_name": "Ana"},
  "season": "2026-2027",
  "teams": [{"id": "…", "name": "Club Norte", "crest": "/media/…", "competition": "snp", "competition_name": "SNP", "has_snp": true,
             "role": "admin", "role_label": "Capitán", "can_manage": true, "division": "500", "division_label": "500"}],
  "upcoming": [{"id": "MAT…", "team_id": "…", "competition": "snp", "competition_name": "SNP", "kind_label": "Jornada 6",
                "date": "2026-11-21", "days_left": 1, "time": "17:00", "location": "Pistas Norte", "maps_url": "https://www.google.com/maps/…",
                "neutral_venue": false, "local": {"name": "Club Norte", "is_own": true}, "visiting": {"name": "Club Este", "is_own": false},
                "me": {"state": "called", "game": 2, "points": 3, "partner": "Laura Gil"}, "web_path": "/match/…"}],
  "suspended_clubs": [],
  "has_player": true,
  "has_history": true
}
```

- `state`: `ok` (tiene equipo), `no_team` (ninguno) o `suspended` (solo tiene clubes suspendidos; sus nombres van en `suspended_clubs`). No cuentan los clubes suspendidos ni los archivados.
- `teams` va en el orden de las competiciones (SNP, LAPI…). `role` es `admin` (capitán), `manager` (gestor) o `member` (jugador); `can_manage` es cierto para capitán y gestor. `crest` y `division_label` son `null` si no hay.
- `upcoming` es el carrusel «Próximo enfrentamiento»: los enfrentamientos abiertos de todos los equipos activos que caen en la semana natural del más cercano (como en la web), por fecha. `time`, `location` y `maps_url` son `null` si no hay (`neutral_venue` quita Local y Visitante). `web_path` es la ficha del enfrentamiento en la web (se abre con `/auth/web-session`).
- `pending` es el «Pendiente» de quien gestiona: `rows[]` son los enfrentamientos abiertos de los equipos que gestiona, vencidos (`overdue`) y los de los próximos 14 días, por fecha (`match_id`, `team_id`, `competition`, `competition_name`, `rival`, `date`, `status_label`, `action`: `create_call`, `close_call`, `create_games`, `enter_results` o `close_match`; `action_label` y `web_path`, que va directo al paso que toca); `far` cuenta los de más adelante, que no se listan; `page_size` (3) es el tamaño de página de la web.
- `todos[]` es «Tus pendientes» del jugador: `kind` (`link`, `photo`, `partner`, `availability`), `text` ya traducido, `team_id` y `web_path`. `pending_count` (filas de `pending` más `todos`) es el número de la campana.
- `my_form` es la tarjeta «Mi forma» (suma las fichas de la cuenta en todas sus competiciones, como la web): `null` si no hay ficha enlazada, `{"hidden": true}` si la ocultó, y si no `season`, `stats_path` (Mis estadísticas en la web), `empty`, `has_snp`, `wins`, `losses`, `by_competition[]` (solo con varias competiciones: `code`, `name`, `wins`, `losses`, `called`, `played`, `played_pct`), `last_games[]` (`won`, `code`; del más antiguo al más reciente), `run` (`kind` `V` o `D` y `count`; la racha se muestra con 2 o más), `called`, `played`, `played_pct` y `snp` (`score`, `delta` y `chart`: `path` es el trazado escalonado en % del lienzo con `y` hacia abajo, `points[]` con `x`, `y`, `score`, `date`, más `low`, `high` y `start`; `chart` es `null` sin histórico suficiente).
- `notices[]` son los avisos del Inicio, en el orden de la web: `email` (cuenta con contraseña y email sin confirmar; `email`), `copy_invitation` (invitación de una ficha: `token`, `club` con `name`, `competition` y `competition_name`, `invited_by`, `player_name` y `returning`, que es cierto si vuelve a un equipo que dejó), `manager_welcome` (gestor recién nombrado: `team_id`, `team_name`, `has_snp`) y `manager_tip` (capitán de un equipo sin gestor y con otros miembros con cuenta a quienes nombrar: `team_id`, `team_name`). `todos[]` de tipo `availability` trae además `match_id` y `answer` (`null` sin responder o `maybe`: quien responde «Pendiente» sigue viéndolo en «Tus pendientes» hasta que diga Sí o No).
- `POST /api/v1/account/resend-verification` reenvía el email de confirmación (`{"sent": bool}`; 429 con el límite por IP de la web, 502 `email_failed`).
- `POST /api/v1/copy-invitations/<token>` con `{"action": "accept" | "decline"}` acepta o rechaza la invitación de una ficha (`{"accepted": bool}`; 404 si ya no está pendiente para la cuenta; 409 `invitation_error` si no se puede aceptar).
- `POST /api/v1/home/dismiss` con `{"notice": "manager_welcome" | "manager_tip", "team_id"?}` cierra la bienvenida de gestor (con `team_id`) o el aviso «Añade un gestor» (`{"dismissed": true}`).
- `GET /api/v1/matches/<id>` devuelve la ficha del enfrentamiento: `match` (equipos, fecha, lugar, `status_label`, `countdown`, `web_path`), `outcome` (solo con el acta cerrada: `code` V/D/E, `own`, `rival`, `league_points`), `steps[]` (cuatro fases `done`/`cur`/`todo`), `me` (mismos estados que `upcoming[].me`), `can_manage`, `primary` (solo quien gestiona: `key`, `label`, `web_path`, `enabled`, `reason`), `call` (apuntados o convocados, mínimo y suplentes), `games[]` (parejas propias con `state` y `score` si hay resultado), `answer` (`can_answer`, `value`, `comment`) y, para quien gestiona con convocatoria, `availability.counts`. 404 si no es de un equipo activo de la cuenta.
- `POST /api/v1/matches/<id>/availability` con `{"answer": "yes" | "no" | "maybe", "comment"?}` responde si el jugador puede jugar (el comentario solo se guarda con `maybe`; 404 si el enfrentamiento no es de la cuenta o no tiene ficha allí; 409 `closed` con la convocatoria cerrada).
- `POST /api/v1/home/my-form` con `{"hide": true | false}` oculta o vuelve a mostrar «Mi forma» (la misma preferencia que la web) y devuelve `{"hidden": …}`.
- `setup[]` es la configuración del capitán o gestor, un bloque por equipo con algo que hacer (vacío si no hay nada): `team_id`, `team_name`, `competition`, `is_captain`, `snp_account_path` y, con las mismas condiciones que la portada web, `onboarding` («Primeros pasos», solo capitán: `done`, `total`, `percent` y `steps[]` con `key`, `title`, `help`, `action`, `path`, `done`, `alt_action` y `alt_path`), `season_prep` («Prepara la temporada», julio-octubre: `label`, `done`, `total`, `percent`, `is_captain` y `steps[]` con `key` `roster`, `snp` o `rivals`, `done`, `skipped`, `manual`, `captain_only`, `action`, `path`; el de SNP añade `has_account`, `sync` y `request_open`/`request_date`), `club_details` (solo capitán y mientras el equipo no tenga sede: `location`, `default_time` «HH:MM» o `null`), `snp_missing` (el capitán no ha registrado su cuenta SNP) y `snp_sync` («Sincronizar datos»: `state` `idle`, `running`, `ready` o `failed`, `message`, `can_retry`, `blocked`, `service_off`, `same_account`, `attempted_at` (fecha y hora ISO del último intento, `null` si no hubo), `wait_label` (fecha y hora a partir de la que se puede reintentar, «20/11/2026 18:30»), `team_fix_path`). Los `path` son rutas web con `?en=<competición>` para abrirlas en la app.
- `POST /api/v1/home/setup/onboarding/dismiss` con `{"team_id"}` cierra «Primeros pasos» (solo capitán). `POST /api/v1/home/setup/season-prep` con `{"team_id", "action": "mark" | "close", "key"?}` marca `roster`, `rivals` (capitán o gestor) o `snp_skipped` (solo capitán), o la oculta con `close` (solo capitán). `POST /api/v1/home/setup/snp-sync` con `{"team_id"}` lanza «Completar equipo» como la web (`{"started": bool}`; 409 `no_account`, `closed`, `same_account`; 429 `wait` o `rate_limited`; 503 `service_off`). `POST /api/v1/home/setup/club-details` con `{"team_id", "location", "default_time"?}` guarda la sede (obligatoria) y la hora habitual del equipo propio (solo capitán; `400 validation_error` con `fields`; `{"ok": true}`). `POST /api/v1/home/setup/snp-request` con `{"team_id", "note"?}` pide la actualización a Zyra (`{"created": bool}`). 403 si el rol no basta y 404 si el equipo no es de la cuenta.
- `upcoming[].me` es el estado de la cuenta en la convocatoria: `null` si no aplica (capitán o gestor sin ficha enlazada); `{"state": …}` con `unlinked` (sin ficha enlazada), `no_call` (aún no hay convocatoria), `applied_open` (apuntado, convocatoria abierta), `called` (convocado: `game`, `points` en juego y `partner`), `called_no_pair` (convocado, parejas sin decidir), `not_called` o `not_called_open`.
- `display_name` es el nombre de pila o, si no hay, el usuario. `has_player`: tiene ficha enlazada en un equipo activo. `has_history`: como en `/ping`.

### `POST /auth/login`

Cuerpo: `{"login": "usuario o email", "password": "…", "device_name": "iPhone de Ana"}` (`device_name` opcional, hasta 100 caracteres).

Respuesta **201**:

```json
{"token": "zyra_…", "device": "DVTxxxxxxxxxxxx", "expires_at": "…", "user": {"username": "ana", "email": "ana@example.com"}, "team": {"name": "Club Norte", "crest": "/media/…"}}
```

`team` es el equipo propio del primer club de la cuenta (`null` si no tiene club); `crest` es la ruta o URL del escudo (`null` si no hay). Lo devuelven igual `/auth/apple`, `/auth/google` y `/club/register`.

- `401 invalid_credentials`: mismo mensaje para cuenta inexistente, contraseña mala o cuenta desactivada.
- `429 login_locked`: el freno de contraseñas es el mismo que el de la web (5 fallos por IP y usuario, 30 por cuenta, 15 min); `Retry-After` indica los segundos. Los fallos en la web y en la app se suman.

### `POST /auth/register`

Crea una cuenta sin club: la de un jugador que espera la invitación de su capitán. Cuerpo: `{"email": "ana@example.com", "password": "…", "username": "ana", "device_name": "iPhone de Ana"}`. `username` y `device_name` son opcionales.

Sin `username` (o vacío) el servidor genera uno libre a partir del email (la parte anterior a la `@`, con un número si ya existe). La app no lo pide: se cambia en el perfil y el acceso acepta usuario o email. Con `username` se usa tal cual, con las reglas de la web.

Respuesta **201** igual que `/auth/login`, con `team` a `null`; se envía el correo de confirmación.

- `400 validation_error` con `fields` (`account.email`, `account.password`, `account.username`) si algún dato no cumple las reglas de la web.
- `429 rate_limited`: mismo límite de altas por hora que la web.

### `POST /auth/apple`

Cuerpo: `{"identity_token": "<jwt>", "nonce": "<valor en claro>", "first_name"?, "last_name"?, "device_name"?}`. Respuesta **201** igual que el login.

- **Desactivado por defecto**: sin `APPLE_CLIENT_IDS` responde `404 not_found`.
- El `identity_token` lo genera iOS (no el servidor). `nonce` es el valor aleatorio **en claro**; a Apple se le pasa su SHA-256 en hexadecimal.
- Cuenta: la ya enlazada a esa identidad de Apple; si no, la que tenga el mismo email **solo si** Apple lo verificó y la cuenta lo tenía verificado; si no existe, se crea sin contraseña.
- `401 invalid_apple_token`: firma, app, caducidad o nonce incorrectos, o token ya usado (cada token vale una vez).
- `403 apple_email_unverified`, `403 email_blocked`.
- `409 apple_account_unconfirmed`: existe una cuenta con ese email sin confirmar; no se enlaza ni se crea nada.
- `503 apple_unavailable`: el servidor no pudo obtener las claves de Apple; reintenta.
- Apple da nombre y email solo la primera vez que una persona autoriza la app: envía `first_name` y `last_name` en esa primera llamada.

### `POST /auth/google`

Cuerpo: `{"id_token": "<jwt>", "nonce": "<valor en claro>", "device_name"?}`. Respuesta **201** igual que el login.

- **Desactivado por defecto**: sin `GOOGLE_IOS_CLIENT_IDS` (ID de cliente OAuth de tipo iOS, separados por comas) responde `404 not_found`. Es independiente del `GOOGLE_CLIENT_ID` del botón de la web.
- La app obtiene el `id_token` con el flujo OAuth nativo (`ASWebAuthenticationSession`, PKCE, `scope=openid email profile`) y envía a Google el `nonce` en claro; Google lo devuelve tal cual dentro del token. El nombre sale del propio token.
- Cuenta: la ya enlazada a esa identidad de Google (la misma de la web, `allauth`); si no, la que tenga el mismo email (Google lo verificó), igual que en la web: si la cuenta no tenía ese email verificado, se anula su contraseña y se borran sus otros emails y conexiones; si no existe, se crea sin contraseña.
- `401 invalid_google_token`: firma, app, caducidad o nonce incorrectos, o token ya usado (cada token vale una vez).
- `403 google_email_unverified`, `403 email_blocked`.
- `503 google_unavailable`: el servidor no pudo obtener las claves de Google; reintenta.

### `GET /club/options`

Datos del formulario de alta: `competitions` (cada una con `code`, `name`, `full_name`, `color`, `snp` —si admite conectar la cuenta de SNP—, `divisions` y `countries` como `{code, label}`), `genders`, `google` (si se puede continuar con Google) y `snp_available`.

### `POST /club/register`

Alta de club desde la app, con las mismas reglas que la web. Cuerpo:

```json
{
  "team": {"name": "", "location": "", "competition": "snp", "gender": "M", "country": "ES", "division": "500",
           "default_time": "20:30", "crest": "<imagen en base64, opcional>"},
  "captain": {"mode": "manual", "name": "", "last_name": ""},
  "account": {"username": "", "email": "", "password": ""},
  "device_name": "iPhone"
}
```

- `team.location` (sede) y `account.username` son opcionales: sin sede el equipo queda sin ella (la web sigue pidiéndola) y sin usuario el servidor genera uno libre a partir del email.
- `captain.mode` es `manual` (con `name` y `last_name`) o `snp` (con `snp_username` y `snp_password`; solo en competiciones con SNP: en las demás se ignora).
- En lugar de `account`, `"google": {"id_token", "nonce"}` usa la cuenta de Google (nueva o ya existente) sin contraseña.
- `team.crest`: imagen en base64 (hasta ~2,2 MB); se reduce y valida igual que en la web.
- Con éxito, 201 como el login, más `club` (`name`, `competition`) y, con SNP, `next_path`: la página web donde se elige qué jugador es el capitán (se abre con `/auth/web-session`); si SNP está apagado, `snp_unavailable: true`.
- `400 validation_error` con `fields`: errores por campo con clave `seccion.campo` (`team.name`, `captain.snp_username`, `account.email`, `account.password`, `team.crest`…), cada uno una lista de textos.
- `409 space_taken`: la cuenta ya tiene equipo en esa competición. `403 email_blocked`. `429 rate_limited`: 5 altas por hora y por IP (el mismo límite que la web). Errores de Google como en `/auth/google`.

### `GET /invitations/<token>` y `POST /invitations/<token>/accept`

Con token. `<token>` es el de la invitación del enlace web `/invite/<token>/` (la app acepta el enlace entero o solo el código).

- `GET`: 200 `{"club": {"name", "competition", "crest", "captains": [..]}, "can_join": bool, "message": "…"}`. `can_join` es falso (con `message`) si la cuenta ya está en ese equipo o ya tiene sitio en esa competición. `404 not_found` si el código no existe; `410 invitation_invalid` si ya se usó, caducó o el club está suspendido.
- `POST`: une a la cuenta al equipo con las mismas reglas que la web y manda el correo de bienvenida. 201 `{"club", "team", "next_path"}`; `next_path` es la página web donde se elige qué jugador eres (se abre con `/auth/web-session`). `409 invitation_error` si no se puede (ya usada, ya es miembro, ya tiene equipo en la competición).

### `GET /.well-known/apple-app-site-association`

Fuera de `/api/v1/`. Para los enlaces universales: responde 404 hasta definir `APPLE_APP_LINK_IDS` (`TEAMID.bundle.id`, separados por comas); con ello sirve el JSON que Apple pide, con la ruta `/invite/*`. Hace falta además la capacidad Associated Domains en la app (cuenta de pago de Apple).

### `POST /auth/logout`

Respuesta 200: `{"revoked": true}`. Revoca también el registro push y las sesiones web que ese dispositivo abrió con `/auth/web-session`. El siguiente uso del token da 401.

### `POST /auth/web-session`

Cuerpo opcional: `{"next": "/ruta/"}` (ruta relativa de la web; por defecto `/`; no puede ser otro dominio, `//` ni la propia API → `400 invalid_next`).

Respuesta **201**: `{"url": "https://…/app/session/<ticket>/", "expires_at": "…"}`.

- La app debe abrir esa URL **de inmediato** en su navegador interno con el User-Agent `ZyraApp/<versión>` (la web oculta cabecera y menú con ese User-Agent).
- El ticket dura 60 s y vale una sola vez. Solo se canjea con ese User-Agent, así que un navegador o una vista previa de enlaces no lo gasta.
- Cerrar sesión en la app cierra también esa sesión web. Límite: 10 tickets por minuto y token.

### `POST /devices` y `DELETE /devices`

`POST` cuerpo: `{"apns_token": "<hex>", "environment": "production" | "sandbox", "app_version": "1.0.0"}` (`environment` por defecto `production`; `app_version` opcional).

- Respuesta `{"registered": true, "environment": "production"}`: **201** la primera vez y **200** al repetirlo o si APNs cambia el token (idempotente).
- Si ese token de APNs estaba en otra cuenta del mismo teléfono, pasa a esta.
- `DELETE` responde `{"registered": false}` aunque no hubiera registro.
- Todavía **no se envía ninguna notificación**: solo se guardan los tokens.

### `POST /account/delete`

Cuerpo: `{"confirm": "<contraseña>", "delete_player": false}`. `confirm` es la contraseña o, en las cuentas sin contraseña (Apple/Google), el nombre de usuario. `delete_player: true` elimina también su ficha de jugador; si no, la ficha queda en el club sin cuenta ni foto.

Respuesta 200: `{"deleted": true}`. Revoca todos los dispositivos y borra la cuenta en una sola transacción, con las mismas reglas que la web.

- `409 account_blocked`: el capitán debe traspasar antes la capitanía (o, si es el único miembro, abandonar el club); el personal de Zyra no puede. `detail` trae el motivo para mostrarlo.
- `403 confirmation_failed`: contraseña (o usuario) incorrectos.
- `429 rate_limited`: 5 intentos por hora y usuario.
- **Pendiente para la App Store**: Apple exige revocar su token de Apple al borrar una cuenta creada con Apple; hace falta la clave `.p8` del Developer Portal y todavía no está hecho.

## Códigos de error

| HTTP | `error` | Cuándo |
|---|---|---|
| 400 | `invalid_json` | El cuerpo no es un objeto JSON |
| 400 | `invalid_field` | Falta un campo, no es texto, es muy largo o no cumple el formato; `detail` nombra el campo |
| 400 | `validation_error` | Errores del formulario de alta; `fields` los da por campo |
| 400 | `invalid_next` | Destino de `web-session` no válido |
| 401 | `unauthorized` | Sin token, caducado, revocado o inexistente (`WWW-Authenticate: Bearer`) |
| 401 | `invalid_credentials` | Login fallido |
| 401 | `invalid_apple_token` | Token de Apple no válido, repetido o de una cuenta desactivada |
| 401 | `invalid_google_token` | Token de Google no válido, repetido o de una cuenta desactivada |
| 403 | `confirmation_failed` | Confirmación de borrado incorrecta |
| 403 | `apple_email_unverified`, `google_email_unverified`, `email_blocked` | Ver `/auth/apple` y `/auth/google` |
| 404 | `not_found` | Ruta desconocida, o Apple o Google sin configurar |
| 405 | `method_not_allowed` | Método no permitido (`Allow` lo indica) |
| 410 | `invitation_invalid` | Invitación usada, caducada o club suspendido |
| 409 | `invitation_error` | La invitación no se puede aceptar |
| 409 | `account_blocked`, `apple_account_unconfirmed`, `space_taken` | Ver cada endpoint |
| 429 | `rate_limited` | Demasiadas peticiones (`Retry-After` en segundos) |
| 429 | `login_locked` | Frenos de login |
| 503 | `apple_unavailable`, `google_unavailable` | Sin respuesta de Apple o de Google |

## Límites

Por minuto y proceso del servidor (se ajustan por entorno): **120 por token** (`API_RATE_LIMIT_PER_MINUTE`), **30 por IP** en rutas públicas
(`API_PUBLIC_LIMIT_PER_MINUTE`) y **30 por IP con tokens inválidos** (`API_AUTH_FAILURES_PER_MINUTE`). Al pasarse: `429 rate_limited` con `Retry-After`.
La web no se ve afectada: `/api/` está fuera del freno general por IP.

## Iniciar sesión con Apple desde la app (Swift)

```swift
import AuthenticationServices
import CryptoKit

let rawNonce = UUID().uuidString + UUID().uuidString          // aleatorio, en claro
let hashed = SHA256.hash(data: Data(rawNonce.utf8)).map { String(format: "%02x", $0) }.joined()

let request = ASAuthorizationAppleIDProvider().createRequest()
request.requestedScopes = [.fullName, .email]
request.nonce = hashed                                          // a Apple, el SHA-256

// En el delegado, al recibir el ASAuthorizationAppleIDCredential `credential`:
let identityToken = String(data: credential.identityToken!, encoding: .utf8)!
// POST /api/v1/auth/apple con:
// {"identity_token": identityToken, "nonce": rawNonce,
//  "first_name": credential.fullName?.givenName, "last_name": credential.fullName?.familyName}
```

## Probar en local desde el móvil (túnel)

La app exige `https://` y un iPhone no alcanza el `127.0.0.1` del Mac, así que se expone el servidor local con un túnel (ngrok o cloudflared) y se arranca con:

```
SITE_URL= DJANGO_DEBUG=True DJANGO_BEHIND_PROXY=True \
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,<dominio-del-túnel> \
DJANGO_CSRF_TRUSTED_ORIGINS=https://<dominio-del-túnel> \
python manage.py runserver 8000
```

- `SITE_URL=` vacío: si el `.env` lo tiene definido, Django redirige con un 301 a ese dominio y el móvil no puede seguirlo.
- `DJANGO_BEHIND_PROXY=True`: Django usa `X-Forwarded-Proto` y `web-session` devuelve una URL `https://` (con `http://` iOS la bloquea en el navegador interno).

## Lista de validación (probar la app contra el servidor)

Prueba en un entorno desplegado desde `zyra-ios`, no en producción. Sustituye `$H` por el dominio de `SITE_URL`.

1. **Login** `curl -X POST $H/api/v1/auth/login -H 'Content-Type: application/json' -d '{"login":"…","password":"…","device_name":"Pruebas"}'` → 201 con `token`. Guarda `zyra_…`.
2. **Ping** con `-H "Authorization: Bearer zyra_…"` → 200; sin cabecera → 401 `unauthorized`.
3. **Login fallido**: contraseña mala → 401 `invalid_credentials`; a los 5 fallos seguidos → 429 `login_locked`.
4. **Ruta inexistente** `GET /api/v1/nada` → 404 JSON (no HTML); `GET /api/v1/auth/login` → 405 con `Allow`.
5. **Push**: `POST /devices` con un `apns_token` de 64 hex → 201; repetir → 200; `DELETE /devices` → 200.
6. **Puente a la web**: `POST /auth/web-session` → `url`; abrirla **con User-Agent `ZyraApp/1.0`** → entra ya autenticado y sin cabecera ni menú; abrirla otra vez → no sirve; a los 60 s → no sirve.
7. **Logout**: `POST /auth/logout` → 200; repetir el `ping` → 401; la sesión web abierta en 6 queda cerrada.
8. **Cambio de contraseña**: con dos dispositivos, cambia la contraseña en la web → ambos tokens dan 401.
9. **Apple** (con `APPLE_CLIENT_IDS` configurado): desde la app, primer acceso → 201 y cuenta nueva; segundo acceso (otro token de Apple) → 201 en la misma cuenta; repetir el mismo token → 401.
10. **Borrar cuenta**: con una cuenta de prueba que no sea capitán → `POST /account/delete` con la contraseña → 200 y el token deja de servir; con un capitán → 409 con el motivo; con contraseña mala → 403.
11. **Web intacta**: iniciar sesión, cambiar la contraseña y eliminar la cuenta en la web siguen funcionando igual.
