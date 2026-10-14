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
- [V] Un club tiene un único capitán (restricción `unique_captain_per_club`). Se cede con
  `transfer_captaincy` (vista `transfer_captaincy_view`) solo a un miembro enlazado a un `Player` del club
  (`eligible_successors`); el antiguo pasa a miembro y se borra la `SnpAccount` del club (eran sus credenciales) y se reabre «Primeros pasos»
  (`onboarding_dismissed_at=None`), que incluye la tarea «Registra tu cuenta de SNP». El capitán no puede quitarse ni abandonar sin ceder antes.
- [V] Eliminar la cuenta («Mi perfil», `delete_account`): un capitán debe ceder antes la capitanía
  (`account_delete_blocker`); la ficha de jugador se desenlaza (o se borra si se elige). El capitán
  solo puede eliminar el club tras desvincular todas las demás cuentas. Tests: `core/tests_account_lifecycle.py`.
- [V] Un jugador solo puede jugar en clubes de una categoría; la pertenencia a un club es única por cuenta (regla anterior).
- [V] No hay aprobación del capitán al unirse por enlace de invitación (decisión de producto).
- [V] Si el único miembro abandona, el club se borra entero tras escribir su nombre exacto
  (`club_name_matches`, `delete_club`). Tests: `core/tests_delete_club.py`.
- [V] Quitar o abandonar desenlaza su `Player` (`remove_membership`); el jugador y sus estadísticas quedan.
- [V] Alta de club: crea equipo propio (`is_own=True`, `in_group=True`) y membresía de capitán;
  el jugador del capitán se crea escribiendo su nombre o eligiéndolo del equipo traído de SNP (`CaptainSnpForm`).
- [V] Login con usuario o email (`ACCOUNT_LOGIN_METHODS`); verificación de email opcional
  (`ACCOUNT_EMAIL_VERIFICATION='optional'`, aviso y reenvío en «Mi perfil», `core/email_verification.py`). Google con un
  email existente entra en esa cuenta (`SOCIALACCOUNT_EMAIL_AUTHENTICATION_AUTO_CONNECT`); si el email local no estaba
  verificado se invalida su contraseña (`core/adapters.py`). Tests: `core/tests.py`.
- [V] Frenos en caché compartida (`core/ratelimit.py`, tabla `django_cache`; IP real con `TRUSTED_PROXY_COUNT`): login
  5 fallos → 15 min, registro, invitaciones, comprobación de contraseña y reenvíos (429).
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
  (`manage_teams`) trata los rivales, del grupo y dados de baja (`in_group=False`), que se vuelven
  a dar de alta allí o desde el aviso de nombre parecido (`reactivate_team`, POST).
- [V] El equipo propio nunca sale del grupo: `Team.save`, `Teamform.clean` y la migración
  `team/0006` lo fuerzan. Al crear un equipo se avisa de nombres parecidos aunque estén de baja.

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
   fija `Match.result` (valores canónicos en `match/outcomes.py`; `EMPATE` posible, p. ej. 6/6) y `result_points`,
   y cierra `Game.draft_mode`. Siempre son 5 partidos: no se contempla un acta con menos. Todo en una transacción.
7. **Reabrir acta** (`reopen_match`, POST, capitán): vuelve a borrador, resultado `NONE`, anota `reopened_at/by`.

Con el acta cerrada [V]: no se borra el partido (`delete_match`) ni su convocatoria (`delete_call`),
ni se editan parejas (`edit_game_match`).

- [V] Advertencias (`create_penalty`): solo a jugadores del club con `in_team=True`.
- [V] Alineación sugerida (`suggested_lineup`, `match/advisor.py`): solo propone, no guarda.

## Informe PDF y correos

- [V] Informe mensual del jugador (`match/monthly_email.py`, `match/monthly_report.py`, `match/monthly_pdf.py`): `send_monthly_reports`
  manda el PDF del mes natural anterior a cada cuenta enlazada a un jugador (club no suspendido, email, `UserPreference.monthly_report`
  activo) que jugó partidos ese mes; `monthly_scope` (`todos`/`competitivos`) filtra los amistosos. Idempotente por
  `MonthlyReportDelivery(user, month)`: se reserva antes de enviar y se borra si el correo falla. El correo lleva enlace de baja con token
  firmado sin caducidad (`core/unsubscribe.py`, vista `monthly_unsubscribe`: GET confirma, POST con CSRF desactiva; cabecera
  `List-Unsubscribe`). El PDF (2 páginas) añade convocatorias del mes (`monthly_calls`: apuntado y alineado / apuntado sin jugar /
  no apuntado, solo cerradas), evolución de `SnpScoreHistory` del mes (`monthly_snp`) y el panel «Sets clutch» (`set_stats`).
  Envío manual: `send_monthly_reports --user EMAIL [--month]` (opciones del job en backoffice) se salta la idempotencia y la baja,
  respeta el alcance y suma `MonthlyReportDelivery.manual_sends`/`last_manual_at`. Necesita `SITE_URL`. Programado en `JOBS` (`0 9 1 * *`); sin `run_scheduler`, un cron mensual del host que
  ejecute `python manage.py send_monthly_reports`. Tests: `match/tests_monthly.py`.

- [V] Al cerrar la convocatoria se encola un `ReportDelivery` por capitán con email
  (`match/notifications.py`); se intenta al momento y `send_call_reports` reintenta a los 2, 10,
  30 y 120 min (`RETRY_DELAYS`); tras 5 intentos queda `failed` y se avisa al personal.
- [V] El PDF intenta caber en 2 páginas probando `LAYOUTS` cada vez más densos; si no cabe,
  numera sobre el total real (`match/report_pdf.py`, `render_report`). Tests: `match/tests_report.py`.
- [V] `Match.report_scope` (`todos`/`competitivos`, se elige al crear el partido y no se edita; por defecto
  `UserPreference.report_scope` de «Mi perfil») decide qué historia usa el informe: con `competitivos`
  `match/report.py` excluye los amistosos del registro de parejas, balance, precedentes y convocatorias.
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
- [V] «Completar equipo» desde la web: solo UNA vez con éxito (en el alta o con la cuenta SNP ya registrada;
  `snp_import.web_import_done`), máx. 3 búsquedas al día con 5 min entre ellas. Cada búsqueda fallida suma a
  `Club.snp_import_failures` (no cuenta si el servicio SNP está apagado); al llegar a `MAX_FAILED_SEARCHES` (3) la
  opción se oculta (`web_blocked`), se avisa al capitán de que el administrador ha sido notificado y al personal
  por email + auditoría `club.snp_import_blocked`. Después solo el back-office o el proceso automático
  (`players/snp_import.py`); el personal repone el contador desde la ficha del club. Los clubes con `Club.snp_unlimited` (editable en el back-office, ficha del club)
  no tienen límite. La búsqueda se encola (`SnpTeamImport` RUNNING sin `started_at`) y la procesa el trabajo
  `process_snp_imports` (cada minuto), no el proceso web.
- [V] Interruptor `ServiceSwitch` «snp» (back-office → Servicios): apagado, se bloquean sincronización y «Completar
  equipo» y el usuario ve que el servicio no está disponible. 3 fallos seguidos avisan por email al administrador
  (`players/snp_service.py`, repetición cada 6 h como máximo).
- [V] La temporada empieza el 1 de agosto (`SEASON_START_MONTH`). Al confirmar crea los que faltan y actualiza puntos de los existentes. Además lee en SNP «Competiciones → Clasificación» y crea como `in_group` (género/país/división/sede del equipo propio) los equipos del grupo que no existan (`core.similarity.is_similar`, sin duplicar); los existentes fuera del grupo se dan de alta en él, y si el club no tiene equipo propio, el que SNP marca en negrita lo será. Si ese paso falla no bloquea la importación de jugadores. Tests: `players/tests.py`.

## Estadísticas

- [V] Solo cuentan partidos con el acta cerrada (`pairs.club_game_log`, `calculate_match_statistics`).
- [V] Una pareja es la misma con independencia de quién juegue en cada lado (`pairs.pair_key`);
  los rankings exigen un mínimo de partidos (`min_games_pair`).
- [V] Filtro de tipo: Todos / Competitivos / Amistosos (`?match_type=`); temporada `?season=` (equipo, jugador y parejas; sin ella, todas las temporadas).
- [I] Las métricas se calculan en Python sobre el log de partidos; con muchos partidos por club
  conviene vigilar el rendimiento.

## Fotos, moderación y bloqueos

- [V] Toda foto se valida, reduce y pasa a WebP (`core/images.py`, `process_image`); al cambiarla
  o borrar el objeto se borra el fichero antiguo (`connect_photo_cleanup`).
- [V] Con Rekognition activo, las rechazadas no se guardan; sin él (por defecto) quedan
  «Pendiente de revisar» para el personal (`PhotoCheck`). Tests: `core/test_images.py`.
- [V] Emails bloqueados (`core/blocklist.py`) no pueden registrarse, unirse ni ser invitados.
  Tests: `core/tests_blocklist.py`.
- [V] Cuentas sin confirmar (back-office › «Emails sin confirmar», `backoffice/views.py` `unverified_*`): se listan las cuentas no staff cuyo email no está verificado en allauth (`email_verification.unverified_users`). «Avisar» manda el enlace de confirmación y un plazo (`UNVERIFIED_ACCOUNT_DEADLINE_DAYS`, 7 por defecto, editable por aviso). Eliminar solo si el último aviso ya venció y se escribe el usuario; usa `delete_account` (un capitán pendiente no se borra). Cada aviso y eliminación queda en `AccountNoticeLog`. Sin plazo automático: todo manual. Tests: `backoffice/tests.py`.

## Idioma y accesibilidad

- [V] Español por defecto; inglés solo si se elige en el selector (cookie) o con `?lang=en` en la URL.
  No se mira el idioma del navegador (`LanguageMiddleware`). Tests: `core/tests_i18n.py`, `core/tests_seo.py`.
- [V] Cada página nueva debe añadirse a `core/tests_accessibility.py` (ver `docs/mantener-documentacion.md`).
