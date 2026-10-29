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

- [V] Cada club es el espacio de una competición (`Club.competition`, SNP o LAPI, fija). Una cuenta tiene como mucho un
  espacio (no suspendido) por competición: `core.services.club_of(user, competition)`; lo comprueban `register_club`
  (solo ofrece las competiciones libres, `free_competitions`) y `accept_invitation`/`invitation` (`one_space_message`).
  En espacios sin SNP no hay cuenta SNP, sincronización ni paso de SNP en «Primeros pasos» o «Prepara la temporada».
  Tests: `core/tests_spaces.py`, `core/tests_onboarding.py`, `core/tests_invitations.py`.
- [V] Vistas unidas (`core/spaces.py`): con más de un espacio, Enfrentamientos, Calendario, Inicio (Pendiente y próximo
  enfrentamiento) juntan los espacios con el filtro «Todas · SNP · LAPI» (`?espacio=`, se recuerda en sesión, por defecto
  «Todas»). Cada tarjeta lleva la etiqueta de su competición y sus acciones según el rol en ese espacio.
  Estadísticas nunca mezcla equipos: Equipo, Jugador, Parejas y Rivales son siempre de una competición (chips SNP · LAPI;
  Equipo recuerda la suya en `TEAM_SPACE_KEY`, la primera vez la del primer equipo que gestiona). Lo global es de la persona:
  con jugador enlazado en dos o más espacios (`spaces.linked_players`, `my_stats_available`) hay una primera pestaña
  «Mis estadísticas» (`my_statistics`, `data_analyse/templates/stats_mine.html`, `static/js/stats_spaces.js`) con chips Todas · SNP · LAPI y
  el enlace Estadísticas del menú abre en ella. «Todas» cuenta sus partidos (no puntos) y pone cada competición al lado de
  la otra con su color (sets, local/visitante, ganados por temporada apilados con total, convocatorias en las que se
  apunta); SNP o LAPI (`?espacio=`) redirige a su ficha de jugador en esa competición, que mantiene la pestaña y los chips.
  En la interfaz no se dice «espacio» sino equipo/competición. El menú de usuario solo informa («Tus equipos»: equipo,
  competición y papel; `Membership.team_role_label`) y no cambia de espacio; con varios equipos la cabecera muestra el
  nombre del usuario. El espacio activo cambia sin aviso (`switch_to`): al abrir un enfrentamiento de otro espacio
  (`call_for_match`, `space_match`), con `?en=` (`follow_space`, antes de comprobar el rol) y al elegir competición en
  Estadísticas. Plantilla, Club y Rivales (`management_view`): si gestiona unos espacios y en otros solo juega, solo ve
  los que gestiona; el selector SNP | LAPI sale si gestiona todos o es jugador en todos. El registro muestra desactivadas las
  competiciones en las que ya tiene equipo. Inicio con varios equipos: el banner los enseña todos («Tus equipos»,
  `home_teams`) y «En racha» da tarjetas por equipo (`streaks`); quien es jugador en todos sus equipos no ve Plantilla en
  el menú (`hide_roster_nav`, `spaces.plays_only`); tampoco tiene la ficha de Plantilla (`show_player` lo lleva a las estadísticas del jugador) ni su pestaña «Resumen» en Estadísticas › Jugador, que sí ve con su selector. Jugador, Parejas y Rivales solo eligen SNP o LAPI (sin «Todas»). El informe puede incluir los partidos de la temporada
  en otras competiciones de los convocados con cuenta enlazada (`Match.report_other_competitions`). Tests:
  `core/tests_spaces_unified.py`.
- [V] Se puede crear una cuenta sin club (`register_account`, o Google desde esa página): queda en `no_club` hasta aceptar una
  invitación o registrar un club. Back-office: KPI «Sin club» (`accounts_without_club`: activas y no staff), filtro `?kind=no_club`.
  Tests: `core/tests_account_without_club.py`, `AccountsWithoutClubTests` en `backoffice/tests_ops.py`.
- [V] Rol de gestor (`Membership.MANAGER`, hasta `MAX_MANAGERS`=2 por club): lo nombra y quita solo el capitán (`set_manager`, vista `set_manager_view`). `club_manager_required` (capitán o gestor) protege lo deportivo: enfrentamientos (también eliminarlos con el acta abierta), convocatorias, alineaciones, resultados, cierre de acta, advertencias, jugadores y equipos. `club_admin_required` (solo capitán) protege miembros, invitaciones, traspaso, cuenta SNP, «Completar equipo», reabrir actas, eliminar convocatorias, desenlazar jugadores y eliminar el club. Al traspasar la capitanía los gestores se mantienen; `admin_emails` incluye a los gestores. Prueba: `core/tests_roles.py` (cada URL por rol).
- [V] Un club tiene un único capitán (restricción `unique_captain_per_club`). Se cede con
  `transfer_captaincy` (vista `transfer_captaincy_view`) solo a un miembro enlazado a un `Player` del club
  (`eligible_successors`); el antiguo pasa a miembro y se borra la `SnpAccount` del club (eran sus credenciales) y se reabre «Primeros pasos»
  (`onboarding_dismissed_at=None`), cuyos 3 pasos son «Conecta SNP o añade a tus jugadores» («Añade a tus jugadores» fuera de la SNP), «Invita a tus jugadores» y «Crea tu primer enfrentamiento» (se muestran primero en la portada y ocultan los bloques vacíos mientras queden pendientes). El capitán no puede quitarse ni abandonar sin ceder antes.
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
- [V] Usuario único sin distinguir mayúsculas (validación) y email único en la base de datos (índice `LOWER(email)`, migración `core/0019`); si dos registros chocan, el formulario muestra el error en vez de un 500. Tests: `core/tests_invitations.py`.

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

- [V] Los números del ciclo salen de la ficha de la competición (`core/competitions.py`, `competition_for`): partidos por enfrentamiento y sus puntos, convocados mínimos y partido de desempate. Hay dos: SNP (5 partidos 3-3-2-2-2, 10 convocados, desempate en el 3) y LAPI (3 partidos de 1 punto, 6 convocados, sin empate posible); cada club juega la de su espacio (`Club.competition`). El recomendador `match/advisor.py` recibe la ficha: en la SNP ordena las parejas por puntos SNP; sin `has_snp` (LAPI) usa solo historial y afinidad, sin orden de juego (cruce por sorteo), y la pantalla de parejas y el PDF no muestran puntos ni orden. Por eso mismo (`ordered_pairs=False`) Estadísticas no muestra en LAPI «Por número de partido» (equipo y jugador) ni «Balance de partidos por jugador». Tests: `core/tests_competitions.py`.

Orden obligatorio del ciclo (`match/views.py`) [V], cubierto por `match/tests_flow.py`:

1. **Partido** (`MatchForm`): el equipo propio juega como local o visitante; local ≠ visitante. Selector «Competición» bloqueado en la del espacio (`Club.competition`).
   Tipos según la competición (`Competition.match_types`): SNP Enfrentamiento, Reto, Play Off; LAPI Liga, Playoffs,
   Fase final (los enfrentamientos LAPI antiguos pasaron a Liga, migración match/0015). Solo la liga
   (`league_type`) tiene jornada (`Match.round_number`, opcional) y puntos de liga (`Match.league_points`: LAPI
   ganar 3-0 = 4, 2-1 = 3, perder = 1; total de la temporada en Estadísticas › Equipo, `match/league.py`). En
   Playoffs y Fase final (`final_types`), convocar a quien no ha jugado `finals_min_regular` (2) enfrentamientos de
   liga esa temporada pide marcar «Convocarlos igualmente» (`force_finals`, reglamento LAPI 8.2). Tests: `match/tests_league.py`.
   **No presentado** (competiciones con `no_show`, LAPI; no en amistosos): con el acta abierta, en cualquier
   fase, «Más» › «No se presentó el rival» / «No nos presentamos» (`mark_no_show`, capitán o gestor) borra
   parejas y resultados, guarda `Match.no_show` (`own`/`rival`) y cierra el acta con todos los puntos para el
   que sí se presentó (3-0). Cuenta en el balance del equipo, sus rachas y Rivales (no como mayor victoria o peor
   derrota), no en jugadores, parejas ni asistencia (las consultas de convocatorias filtran `match__no_show=""`); no envía el correo de resultado.
   Puntos de liga: 4 si no se presentó el rival, 0 si no nos presentamos (las sanciones del reglamento no se
   muestran nunca). «Quitar no presentado» (`undo_no_show`) reabre el acta; reabrirla también lo quita.
   Amistoso: `match_type="amistoso"`; puede tener rival escrito a mano (`rival_name`, sin crear
   `Team`, ese lado `NULL`) que no puede llamarse como el equipo propio.
2. **Convocatoria** (mínimo `min_call_players` de la competición al crearla y al editarla: 10 SNP, 6 LAPI): una por partido; si ya existe o el acta está cerrada → `existing_call`.
   Se edita mientras el acta siga abierta (`edit_call` mira `match.draft_mode`); cada cambio se anota en `CallLog`.
3. **Cerrar convocatoria** (`close_call`, POST): ≥10 jugadores y abierta. Siempre se cierra aunque
   falle el envío del informe.
4. **Partidos** (`create_game_for_match`): requiere convocatoria cerrada con ≥10. Alineación
   (`match/lineup.py`): 5 parejas completas, jugadores de la convocatoria, dos distintos por pareja,
   nadie en dos parejas. Partidos 1–2 valen 3 puntos, 3–5 valen 2.
5. **Resultado** (`match/scoring.py`): sets válidos 6-0…6-4, 7-5, 7-6; sin tercer set si una pareja
   gana los dos primeros; con 1-1 el tercero es obligatorio (set normal o super tie-break a 10 con
   2 de diferencia). Con `Result.retired` (partido finalizado por lesión) vale un resultado incompleto
   (`validate_retired_result`, p. ej. 7-5 / 3-0): gana quien va ganando (más sets, luego más juegos).
   En las competiciones con `injury_completes` (LAPI) se indica la pareja lesionada (`Result.injured_side`) y
   gana siempre la sana: `complete_retired_result` le completa el set a medias a 6 (a 7 si la lesionada
   tenía 5 o 6) y los sets que falten 6-0 (3-2 queda 3-6 / 0-6). La casilla y la pareja están en el resultado de un partido y en «Poner resultados» (`match/templates/includes/injury_fields.html`, prefijo `gN_`); la etiqueta «Lesión» dice qué pareja se lesionó.
   Al guardar fija `Game.winner`.
6. **Cerrar acta** (`close_match`, POST): acta abierta y 5 partidos con resultado. Suma puntos,
   fija `Match.result` (valores canónicos en `match/outcomes.py`; `EMPATE` posible, p. ej. 6/6, salvo en Reto y Play Off: ahí el 6-6 lo decide el ganador del partido 3, `determine_match_result`) y `result_points`,
   y cierra `Game.draft_mode`. Con fecha futura exige `confirm_future`. Los resultados se pueden
   meter de una vez en `enter_results` (guardado parcial; «Guardar y cerrar acta»). La fase y la siguiente acción salen siempre de
   `match/phase.py` (`phase_of`/`phases_for`), que usan el inicio, el listado y la página del enfrentamiento. Siempre son 5 partidos: no se contempla un acta con menos. Todo en una transacción.
7. **Reabrir acta** (`reopen_match`, POST, capitán): vuelve a borrador, resultado `NONE`, anota `reopened_at/by`.

Con el acta cerrada [V]: no se borra el partido (`delete_match`) ni su convocatoria (`delete_call`),
ni se editan parejas (`edit_game_match`).

- [V] Advertencias (`create_penalty`): solo a jugadores del club con `in_team=True`. El motivo (`kind`) es obligatorio y «Otro» exige detalle. Solo capitán y gestores las aplican, editan (`edit_penalty`: motivo y detalle, desde el historial de Estadísticas › Advertencias) y retiran (`delete_penalty`, que acepta `next` interno: «Quitar» en el registro de la convocatoria y «Deshacer» en el aviso, que lleva la URL en `extra_tags="undo=…"`); las de otros clubes se ignoran.
- [V] Alineación sugerida (`suggested_lineup`, `match/advisor.py`): solo propone, no guarda. Necesita `players_per_lineup` convocados de la competición (10 SNP, 6 LAPI).
- [V] Dar de baja a todos los jugadores del equipo (`manage_roster`, `edit_player`) se permite, pero avisa antes de guardar y después.
- [V] Crear otro espacio con una cuenta que ya tiene jugador: no se pide el nombre, el nuevo jugador copia nombre y apellidos del primero (`register_club`).

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

- [V] Al cerrar el acta (`do_close_match`) se avisa del resultado por email (`match/result_email.py`): un
  `MatchResultDelivery` por enfrentamiento y miembro activo del club con email (capitán incluido; club no
  suspendido) y `UserPreference.match_result_email` activo (por defecto sí; interruptor en «Mi perfil» y enlace de baja
  firmado `result_unsubscribe` con su propia sal, además de `List-Unsubscribe`). Es cola e idempotencia a la vez: se envía al
  momento y `send_call_reports` reintenta con `RETRY_DELAYS`; solo se avisa en el primer cierre: si el acta se
  reabre y se vuelve a cerrar (`Match.reopened_at`) no se envía nada más salvo que el capitán marque la casilla «Volver a enviar el correo» (`resend_email`, desmarcada por defecto) en la confirmación del cierre. Cuatro cabeceras (victoria, derrota, empate, amistoso, que avisa de que no
  cuenta en lo competitivo) con las 5 parejas, sets y puntos y el partido de quien lo recibe resaltado. Un fallo de envío
  nunca impide cerrar el acta. Back-office: «Salud de los servicios» muestra enviados/fallidos/pendientes, último envío y
  los avisos con problemas; los fallidos de 7 días suben a la bandeja de atención, a las alertas y al resumen semanal. Tests: `match/tests_result_email.py`.
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
- [V] `update_snp_scores`: un ciclo por ejecución, lunes y miércoles 05:00 (Madrid); solo clubes pendientes o
  con fallo reintentable. Fallos de usuario/contraseña no se reintentan solos (evita bloquear la
  cuenta del capitán). Para ante 429/403/503 o fallos de red seguidos.
- [V] Mientras una búsqueda web está en marcha (`SnpTeamImport.RUNNING`) los capitanes ven en toda la web la barra de `core/templates/includes/sync_bar.html` (`progress`/`stage` del import, `sync_status`) y `not_while_syncing` bloquea `create_player`, `create_team` y `create_match`.
- [V] «Prepara la temporada» (`core/season_prep.py`, `Club.season_prep`): tarjeta del Inicio de capitanes y gestores del 1 de julio al 31 de octubre en clubes creados antes del 1 de julio; tres pasos (plantilla y rivales los marca a mano quien los revisa con `season_prep_step`; SNP se marca solo con una búsqueda web correcta de la temporada o con «Omitir este paso», solo capitán). «Ahora no» (`season_prep_dismiss`) solo capitán. Se oculta sola al completar los tres. Dentro de la tarjeta va la tarea de SNP (`sync_task(this_season=True)`), por lo que no sale la tarea suelta «Sincronizar datos». Tests: `core/tests_season_prep.py`.
- [V] «Mi forma» (`data_analyse/my_form.py`): tarjeta del Inicio solo para quien tiene su cuenta enlazada a un jugador (nada nuevo para el capitán que no juega). Solo partidos competitivos (los amistosos no cuentan en nada). Últimos 5 (del más antiguo a la izquierda al más reciente a la derecha), racha, balance (anillo de victorias y derrotas) y convocatorias son todos de la temporada actual: un solo gráfico, «jugadas Y de las X convocatorias cerradas en las que te apuntaste»; SNP = puntos actuales y gráfica a todo el ancho de los últimos 30 días con cada actualización en su fecha, máximo/mínimo y diferencia (`SnpScoreHistory`); el botón de la tarjeta lleva a `player_statistics?en=<competición>&player=`. Con jugador en varias competiciones (`others`) suma partidos y convocatorias de todas (son partidos, no puntos), marca la competición de cada uno de los últimos partidos y da el desglose (`by_competition`); los puntos SNP son del jugador de la SNP y la tarjeta no cambia con el espacio activo. Cada usuario puede ocultarla y volver a mostrarla (`toggle_my_form`, `UserPreference.my_form_hidden`). Tests: `core/tests_my_form.py`.
- [V] «Pedir actualización a Zyra» (`players/snp_requests.py`, `SnpUpdateRequest`): solo el capitán (`snp_update_request`, POST, nota opcional) desde el paso de SNP de «Prepara la temporada» y desde Jugadores; una sola abierta por club. El personal la atiende en `/backoffice/snp-requests/` («Completar equipo» lanza el proceso `complete_snp_team` sin el límite de la web; «Marcar hecha» la cierra y cumple el paso de SNP de la temporada). Con más de `ALERT_OPEN_REQUESTS` (5) abiertas, `backoffice.alerts` envía el correo al personal. Tests: `core/tests_snp_requests.py`.
- [V] «Completar equipo» desde la web: solo UNA vez con éxito por temporada, contada desde el último 1 de julio (en el alta, con la cuenta SNP ya registrada o desde «Prepara la temporada»;
  `snp_import.web_import_done`, `season_window_start`), máx. 3 búsquedas al día con 1 min entre ellas (no cuentan las canceladas ni las rechazadas por cuenta SNP ya corregida; guardar la cuenta SNP con datos distintos pone `snp_import_failures` a 0). Si SNP rechazó la cuenta y no ha cambiado, no se relanza (`account_unchanged_after_failure`); la tarea «Conecta SNP o añade a tus jugadores» solo se marca con una búsqueda web hecha. Cada búsqueda fallida suma a
  `Club.snp_import_failures` (no cuenta si el servicio SNP está apagado); la portada del capitán muestra la tarea «Sincronizar datos» (`snp_import.sync_task`) hasta que haya una búsqueda web hecha: «Sincronizar datos»/«Reintentar» (si no hay bloqueo ni espera), «Ver progreso» y «Cancelar» si está en curso, y «Revisar cuenta SNP»; al llegar a `MAX_FAILED_SEARCHES` (3) la
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

- Un jugador solo cuenta convocatorias (apuntado, alineado, no apuntado; informe mensual incluido) desde su `joined_season`: `players.models.joined_by`. Los partidos jugados son hechos y no se filtran. El selector de convocatoria solo muestra las advertencias de la temporada actual (`call__match__season`); las estadísticas de advertencias siguen el selector de temporada.
- [V] Solo cuentan partidos con el acta cerrada (`pairs.club_game_log`, `calculate_match_statistics`). Las consultas de `Game`/`Call` filtran también `match__draft_mode=False`.
- [V] Una pareja es la misma con independencia de quién juegue en cada lado (`pairs.pair_key`);
  los rankings exigen un mínimo de partidos (`min_games_pair`).
- [V] Rivales (`data_analyse/rivals.py`): se agrupan por equipo (`Team.pk`, no por nombre: mismo nombre en dos divisiones = dos rivales) o, en amistosos con rival escrito a mano, por el nombre sin distinguir mayúsculas; solo enfrentamientos con el acta cerrada. La «Previa» (enfrentamiento y convocatoria) cuenta los cerrados anteriores contra el mismo rival, de cualquier tipo, y no se pinta sin historial; «mejor pareja» exige `MIN_GAMES_PAIR` partidos y alguna victoria.
- [V] Filtro de tipo: Todos / Competitivos / Amistosos (`?match_type=`); temporada `?season=` (equipo, jugador y parejas; sin ella, todas las temporadas).
- [V] Asistencia a convocatorias (`attendance.signup_attendance`): apuntados / (plantilla actual con `joined_by` + los apuntados que ya no están); «Todas» promedia por temporada. Sin historial de plantilla, las bajas que no se apuntaron no cuentan.
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
- [V] Guías públicas `/guia/` (`core/guides.py`, `GUIDES`): cada guía existe en es y en en como plantilla
  `core/templates/guides/<slug>.<idioma>.html` (no pasa por `.po`); título y descripción por idioma en `GUIDES`. Entran en el sitemap
  (`GuidesSitemap`) con hreflang y llevan JSON-LD `Article` + `BreadcrumbList` (`seo.guide_structured_data`). Una guía nueva: añadirla a `GUIDES`,
  crear sus dos plantillas y su URL aparece sola en sitemap, portada y tests de accesibilidad. `/guia/plantilla-convocatoria-padel.pdf` es un PDF
  en blanco público (`build_template_pdf`). La imagen para compartir es `static/zyra/og-image-v2.png` (1200×630, `scripts/make_og_image.py`).
- [V] Pie «Hecho con Zyra · dominio» en el PDF de convocatoria, el informe mensual y los correos (`match.report_pdf.draw_made_with`,
  `core/emails.build_email`); sin `SITE_URL` solo el texto, sin enlace. Tests: `core/tests_seo.py`.
- [V] Cada página nueva debe añadirse a `core/tests_accessibility.py` (ver `docs/mantener-documentacion.md`).

## Temporada por defecto

`core/season_choice.choose_season`: `?season=` válida (o `all`) > última elección de la sesión > temporada actual > «Todas».
Lo usan el listado de enfrentamientos, las estadísticas (equipo, jugador, pareja) y las advertencias.
