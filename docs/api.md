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
| `GET /ping` | no | Comprueba que el token sirve y cuándo caduca |
| `POST /auth/login` | sí | Usuario o email y contraseña → token |
| `POST /auth/apple` | sí | `identity_token` de Apple → token (desactivado hasta configurarlo) |
| `POST /auth/google` | sí | `id_token` de Google → token (desactivado hasta configurarlo) |
| `POST /auth/logout` | no | Revoca el token usado |
| `POST /auth/web-session` | no | URL de un solo uso para abrir la web ya con la sesión iniciada |
| `POST /devices` | no | Registra o actualiza el token de APNs de este dispositivo |
| `DELETE /devices` | no | Retira el registro push |
| `POST /account/delete` | no | Elimina la cuenta |

### `GET /ping`

```json
{"device": "DVTxxxxxxxxxxxx", "expires_at": "2027-02-16T21:10:00+00:00"}
```

### `POST /auth/login`

Cuerpo: `{"login": "usuario o email", "password": "…", "device_name": "iPhone de Ana"}` (`device_name` opcional, hasta 100 caracteres).

Respuesta **201**:

```json
{"token": "zyra_…", "device": "DVTxxxxxxxxxxxx", "expires_at": "…", "user": {"username": "ana", "email": "ana@example.com"}}
```

- `401 invalid_credentials`: mismo mensaje para cuenta inexistente, contraseña mala o cuenta desactivada.
- `429 login_locked`: el freno de contraseñas es el mismo que el de la web (5 fallos por IP y usuario, 30 por cuenta, 15 min); `Retry-After` indica los segundos. Los fallos en la web y en la app se suman.

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
| 400 | `invalid_next` | Destino de `web-session` no válido |
| 401 | `unauthorized` | Sin token, caducado, revocado o inexistente (`WWW-Authenticate: Bearer`) |
| 401 | `invalid_credentials` | Login fallido |
| 401 | `invalid_apple_token` | Token de Apple no válido, repetido o de una cuenta desactivada |
| 401 | `invalid_google_token` | Token de Google no válido, repetido o de una cuenta desactivada |
| 403 | `confirmation_failed` | Confirmación de borrado incorrecta |
| 403 | `apple_email_unverified`, `google_email_unverified`, `email_blocked` | Ver `/auth/apple` y `/auth/google` |
| 404 | `not_found` | Ruta desconocida, o Apple o Google sin configurar |
| 405 | `method_not_allowed` | Método no permitido (`Allow` lo indica) |
| 409 | `account_blocked`, `apple_account_unconfirmed` | Ver cada endpoint |
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
