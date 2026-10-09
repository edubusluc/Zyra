# Reglas de negocio (para asistentes)

Reglas comprobadas en el código (y, donde se indica, cubiertas por tests). Prioriza las que, si se
rompen, causan errores funcionales o datos corruptos. Índice general: `ZYRA_CONTEXT.md`.
Verificado contra `main` el 09/10/2026. [V] comprobado · [I] inferido · [?] pendiente.
Comportamiento visible para el usuario, explicado en lenguaje llano: `docs/funcionalidades.md`.

## Aislamiento entre clubes

- [V] Cada consulta de dominio filtra por `request.club`. Patrones: `match.views.club_match`,
  `club_call`, `club_players` (ignora ids de otros clubes), `get_object_or_404(..., club=request.club)`
  en `players`, `team`, `call`, `callLog`, `penalty`. Un objeto ajeno devuelve 404, no 403.
  Tests: `core/tests_security.py`.
- [V] Clubes suspendidos: sus miembros no pueden usarlos (`CurrentClubMiddleware` los descarta;
  `no_club` lo explica). No se borra nada.
- [V] Miembro (`role=member`) = solo lectura. Toda escritura usa `club_admin_required` (403 con
  `core/templates/403.html`).
- [V] Back-office: no staff → 404 (`backoffice/decorators.py`). Consola SQL e importación: solo superusuario.

## Cuentas y clubes

- [V] Una cuenta pertenece a un solo club (no suspendido): `core.services.club_of`; lo comprueban
  `register_club` y `accept_invitation`. Tests: `core/tests_onboarding.py`, `core/tests_invitations.py`.
- [V] El club siempre tiene al menos un capitán: `is_last_admin` bloquea degradar
  (`update_member`), quitar (`remove_member`) y abandonar (`leave_club`) al último.
- [V] Si el único miembro abandona, el club se borra entero tras escribir su nombre exacto
  (`club_name_matches`, `delete_club`). Tests: `core/tests_delete_club.py`.
- [V] Quitar o abandonar desenlaza su `Player` (`remove_membership`); el jugador y sus estadísticas quedan.
- [V] Alta de club: crea equipo propio (`is_own=True`, `in_group=True`) y membresía de capitán;
  el jugador del capitán se crea escribiendo su nombre o eligiéndolo del equipo traído de SNP (`CaptainSnpForm`).
- [V] Login con usuario o email (`ACCOUNT_LOGIN_METHODS`); sin verificación de email. Google con un
  email existente entra en esa cuenta (`SOCIALACCOUNT_EMAIL_AUTHENTICATION_AUTO_CONNECT`). Tests: `core/tests.py`.
- [V] Freno de login: 5 fallos → 15 min (`LOGIN_MAX_FAILURES`, `LOGIN_LOCKOUT_SECONDS` en `core/views.py`).
- [V] Cambiar el email en «Mi perfil» pide la contraseña actual (`EmailChangeForm`). Tests: `core/tests_profile.py`.

### Invitaciones

- [V] Por email: un solo uso. Enlace compartido (`reusable=True`): varios usos; solo vale el último,
  al generar otro el anterior se caduca (`create_invitation_link`). Ambas caducan a las 24 h.
- [V] `accept_invitation` bloquea la fila (`select_for_update`) y rechaza: usada/caducada, club
  suspendido, email bloqueado, ya miembro, o miembro de otro club.
- [V] No se invita a un email que ya es miembro ni a uno bloqueado (`InviteMemberForm.clean_email`).
- [V] Los capitanes no crean cuentas ajenas: cada jugador crea la suya desde el enlace.

## Jugadores

- [V] Un jugador pertenece siempre al equipo propio y hereda su categoría (`Player.save`, `Team.save`).
- [V] Una cuenta es como mucho un jugador por club (restricción en BD). «Soy yo» (`link_player`) solo
  enlaza jugadores sin cuenta; el capitán puede desenlazar (`unlink_player`). Tests: `players/test_own_player.py`.
- [V] Borrar jugador conserva sus partidos (nombre en `Game.removed_player_names`); antes se avisa
  de lo que se pierde (`delete_player`, plantilla `players/templates/confirm_delete.html`).
- [V] `in_team=False` saca al jugador de la plantilla sin borrarlo; los selectores de convocatoria
  muestran solo `in_team=True` más los ya convocados (`selectable_players`).
- [V] Nombres en mayúsculas al mostrarse (`full_name`, `short_name`); texto plano sin HTML
  (`core/validators.py`). Nombres parecidos → aviso antes de guardar (`core/similarity.py`, cabecera `X-Similar-Check`).

## Equipos

- [V] Un único equipo propio por club (restricción en BD).
- [V] No puede haber dos equipos del club con el mismo nombre normalizado (sin mayúsculas, tildes
  ni signos) en la misma división; los antiguos sin división cuentan para todas (`Teamform.clean`).
- [V] Equipo nuevo del grupo copia categoría, país y división del propio. «Gestionar equipos»
  (`manage_teams`) solo trata equipos del grupo.

## Partidos, convocatorias y actas

Orden obligatorio del ciclo (`match/views.py`) [V], cubierto por `match/tests_flow.py`:

1. **Partido** (`MatchForm`): el equipo propio juega como local o visitante; local ≠ visitante.
   Amistoso: `match_type="amistoso"`; puede tener rival escrito a mano (`rival_name`, sin crear
   `Team`, ese lado `NULL`) que no puede llamarse como el equipo propio.
2. **Convocatoria**: una por partido; si ya existe o el acta está cerrada → `existing_call`.
   Se edita mientras el acta siga abierta (`edit_call` mira `match.draft_mode`); cada cambio se anota en `CallLog`.
3. **Cerrar convocatoria** (`close_call`, POST): ≥10 jugadores y abierta. Siempre se cierra aunque
   falle el envío del informe.
4. **Partidos** (`create_game_for_match`): requiere convocatoria cerrada con ≥10. Alineación
   (`match/lineup.py`): 5 parejas completas, jugadores de la convocatoria, dos distintos por pareja,
   nadie en dos parejas. Partidos 1–2 valen 3 puntos, 3–5 valen 2.
5. **Resultado** (`match/scoring.py`): sets válidos 6-0…6-4, 7-5, 7-6; sin tercer set si una pareja
   gana los dos primeros; con 1-1 el tercero es obligatorio (set normal o super tie-break a 10 con
   2 de diferencia). Al guardar fija `Game.winner`.
6. **Cerrar acta** (`close_match`, POST): acta abierta y 5 partidos con resultado. Suma puntos,
   fija `Match.result` (`EMPATE` posible, p. ej. 6/6) y `result_points`, y cierra `Game.draft_mode`.

Con el acta cerrada [V]: no se borra el partido (`delete_match`) ni su convocatoria (`delete_call`),
ni se editan parejas (`edit_game_match`).

- [V] Advertencias (`create_penalty`): solo a jugadores del club con `in_team=True`.
- [V] Alineación sugerida (`suggested_lineup`, `match/advisor.py`): solo propone, no guarda.

## Informe PDF y correos

- [V] Al cerrar la convocatoria se encola un `ReportDelivery` por capitán con email
  (`match/notifications.py`); se intenta al momento y `send_call_reports` reintenta a los 2, 10,
  30 y 120 min (`RETRY_DELAYS`); tras 5 intentos queda `failed` y se avisa al personal.
- [V] El PDF intenta caber en 2 páginas probando `LAYOUTS` cada vez más densos; si no cabe,
  numera sobre el total real (`match/report_pdf.py`, `render_report`). Tests: `match/tests_report.py`.
- [V] Texto de usuario dentro del PDF se escapa (`report_pdf.esc`).
- [V] Remitente fijo join.zyra@gmail.com; la contraseña solo por `EMAIL_HOST_PASSWORD`.
  Correos y PDF salen en el idioma del usuario; los de procesos programados, en español (`Readme.md`).

## SNP

- [V] Credenciales SNP cifradas con `FIELD_ENCRYPTION_KEY`; cambiar la clave invalida las guardadas.
- [V] Cruce de nombres SNP ↔ jugador sin mayúsculas, tildes, categoría final ni segundo apellido
  ausente (`players/snp.py`, `match_scores`); ambiguos y sin pareja no se actualizan.
- [V] `update_snp_scores`: ciclo semanal desde el lunes 23:00 (Madrid); solo clubes pendientes o
  con fallo reintentable. Fallos de usuario/contraseña no se reintentan solos (evita bloquear la
  cuenta del capitán). Para ante 429/403/503 o fallos de red seguidos.
- [V] «Completar equipo» desde la web: 1 vez al mes, máx. 3 búsquedas al día con 5 min entre ellas
  (`players/snp_import.py`); clubes de `SNP_IMPORT_UNLIMITED_CLUBS` (por defecto «Los Gladiadores»)
  sin límite. Al confirmar crea los que faltan y actualiza puntos de los existentes. Tests: `players/tests.py`.

## Estadísticas

- [V] Solo cuentan partidos con el acta cerrada (`pairs.club_game_log`, `calculate_match_statistics`).
- [V] Una pareja es la misma con independencia de quién juegue en cada lado (`pairs.pair_key`);
  los rankings exigen un mínimo de partidos (`min_games_pair`).
- [V] Filtro de tipo: Todos / Competitivos / Amistosos (`?match_type=`); temporada `?season=`.
- [I] Las métricas se calculan en Python sobre el log de partidos; con muchos partidos por club
  conviene vigilar el rendimiento.

## Fotos, moderación y bloqueos

- [V] Toda foto se valida, reduce y pasa a WebP (`core/images.py`, `process_image`); al cambiarla
  o borrar el objeto se borra el fichero antiguo (`connect_photo_cleanup`).
- [V] Con Rekognition activo, las rechazadas no se guardan; sin él (por defecto) quedan
  «Pendiente de revisar» para el personal (`PhotoCheck`). Tests: `core/test_images.py`.
- [V] Emails bloqueados (`core/blocklist.py`) no pueden registrarse, unirse ni ser invitados.
  Tests: `core/tests_blocklist.py`.

## Idioma y accesibilidad

- [V] Español por defecto; inglés solo si se elige en el selector (cookie) o con `?lang=en` en la URL.
  No se mira el idioma del navegador (`LanguageMiddleware`). Tests: `core/tests_i18n.py`, `core/tests_seo.py`.
- [V] Cada página nueva debe añadirse a `core/tests_accessibility.py` (ver `docs/mantener-documentacion.md`).
