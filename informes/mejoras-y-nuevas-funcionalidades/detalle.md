# Zyra · ficha detallada de cada propuesta (24/10/2026)

Complemento de [`estudio.md`](estudio.md). Cada propuesta lleva: **problema**, **qué verá la persona**, **diseño técnico** (archivos y modelos reales del repo), **reglas y casos límite**, **pruebas**, **riesgos** y **cómo medir si funciona**. Solo propuesta: no hay código. Las rutas marcadas **[I]** son inferidas y hay que confirmarlas al empezar. Alcance: sin nuevas ligas.

## Cómo leer las fichas

- **Tamaño**: S ≈ medio día · M ≈ 1–2 días · L ≈ varios PR. Son estimaciones de trabajo con las pruebas y la documentación incluidas.
- **Lista de cierre común** (se omite en cada ficha, aplica a todas, según `CLAUDE.md` y `ZYRA_CONTEXT.md` § Recetas):
  1. Texto visible con `{% translate %}`/`gettext` + `locale/en/LC_MESSAGES/django.po` (y `djangojs.po` si es JS) + `compilemessages`; prueba `core.tests_i18n`.
  2. Docstrings en español en todo lo nuevo (`scripts/check_docstrings.py`).
  3. Pantalla nueva: URL con `club_required`, `{% block page_title %}`, alta en `core/tests_accessibility.py`.
  4. Formulario POST nuevo: `data-loading-text` (`core.tests_submit_lock`).
  5. Modelo nuevo: `makemigrations` en el mismo PR, `PublicIdModel` si se ve en la URL, filtro por `request.club`, `docs/ai/data-model.md`.
  6. Fila en `ZYRA_CONTEXT.md`, regla en `docs/ai/business-rules.md`, línea en `docs/novedades.md`, `docs/funcionalidades.md` si cambia lo visible; `python scripts/check_ai_docs.py`.
  7. Errores en popup y éxitos en toast, solo desde `base.html`.
- **Orden y dependencias** al final (§ Dependencias).

---

# A. Funcionalidades nuevas

## N1 · Cara a cara por rival y «Previa» del partido

**Problema.** Al convocar, el capitán no ve cómo le fue contra ese rival. Hoy hay filtro por rival en el listado de enfrentamientos, pero ninguna vista agrega resultados por rival. Era E1 + C4 del informe de estadísticas (07/10) y nunca se hizo.

**Qué verá.**
- Una pestaña nueva **Rivales** en Estadísticas (`data_analyse/templates/includes/stats_tabs.html`) con una fila por rival: enfrentamientos jugados, ganados / empatados / perdidos, juegos a favor y en contra, último resultado y fecha. Ordenable por rival, por balance y por último enfrentamiento.
- Ficha del rival: historial de enfrentamientos (enlace a cada acta), marcador por partido 1-5, **mejores parejas contra ese rival** y quién ha jugado más veces contra él.
- Bloque **«Previa»** (3-4 líneas) en la página del enfrentamiento y en la pantalla de convocatoria: «Balance 2-1 · último: ganado 8-4 (12/03) · mejor pareja contra ellos: X + Y (3 de 3)».

**Diseño técnico.**
- Módulo nuevo `data_analyse/rivals.py` (lógica pura, sin vistas) con `rival_summary(club, season, match_type)` y `rival_detail(club, rival_key, season, match_type)`. Reutiliza `pair_stats.club_game_log` y `selected_match_type` para respetar los filtros Todos / Competitivos / Amistosos y la temporada, igual que el resto de pantallas.
- Clave de rival: el `Team` cuando existe (`Match.local`/`visiting` distinto del equipo propio) y, para amistosos con nombre escrito a mano, `Match.rival_name` normalizado con `casefold()`. `Match.rival_label` ya unifica el texto. Un mismo nombre en dos divisiones son dos equipos distintos (regla vigente de `Team`): se agrupan por `Team.pk`, no por nombre.
- Vistas en `data_analyse/views.py`: `rival_statistics` (lista) y `rival_detail`; URLs `rival_statistics` y `rival_statistics/<pid:team>` (+ `?name=` para rival escrito a mano). Decorador `club_required`.
- «Previa»: parcial `match/templates/includes/rival_preview.html` incluido desde la plantilla del enfrentamiento y `create_call.html`/`edit_call.html`. Si el rival no tiene historial, no se pinta (nada de «0-0-0»).
- Sin migración. Una consulta agregada por pantalla; con la página de lista paginada a 30 como Rivales.

**Reglas y casos límite.** Los amistosos cuentan o no según el filtro de tipo (por defecto «Todos», como el resto). Los empates solo existen en `enfrentamiento` (reto y play off no tienen). Si el rival cambió de división, aparecen separados (decisión ya tomada en #50). Enfrentamientos con acta abierta no cuentan. Rival eliminado: `Match.local/visiting` con `on_delete=CASCADE` implica que sus enfrentamientos desaparecen; la ficha no debe romper.

**Pruebas.** `data_analyse/tests_rivals.py`: balance con victorias/empates/derrotas, rival con nombre escrito a mano, mismo nombre en dos divisiones, filtro por temporada y tipo, bloque Previa presente/ausente, aislamiento entre clubes (404 al pedir un equipo de otro club), número de consultas acotado.

**Riesgos.** Pocos datos al principio: mostrar «mínimo 2 enfrentamientos» para destacar «mejor pareja». Confundir «rival» con «equipo del grupo» en el texto: usar «Rivales» como ya hace el menú Club.

**Éxito.** Visitas a la pestaña por club y por semana en la vista «Uso» del back-office; objetivo: que la use ≥ 40 % de los clubes activos el primer mes.

**Tamaño.** S–M · 1 PR.

---

## N2 · Recordatorios y calendario (.ics)

**Problema.** Nadie recibe un aviso antes del partido: el capitán lo gestiona por WhatsApp. Es el sitio donde Zyra puede ahorrar más mensajes. Datos existentes: `Match.start_date`, `Match.start_time` (opcional), `Match.location` y `Call.players`.

**Qué verá.**
1. **Correo de recordatorio** a cada convocado con cuenta (jugador enlazado: `Player.user`), 48 h antes: rival, fecha, hora, lugar con enlace de mapa (`Match.maps_url`), su pareja si la alineación ya está hecha y botón «Añadir al calendario».
2. **Aviso al capitán** a 3 días vista si el enfrentamiento aún no tiene convocatoria cerrada («Faltan 3 días y la convocatoria sigue abierta»), con enlace directo a la pantalla que falta. Reutiliza `match/phase.py` (siguiente acción).
3. **Calendario del club** en «Mi perfil» → «Calendario»: un enlace `webcal://…` que se suscribe una sola vez en Google/Apple Calendar y se actualiza solo (nuevas fechas, cambios de hora, cancelaciones). Botón «Regenerar enlace» si se filtra.
4. En la página del enfrentamiento, botón **«Añadir al calendario»** que descarga el `.ics` de ese partido.
5. Preferencia en «Mi perfil»: «Recordatorio del enfrentamiento» (activada por defecto, con enlace de baja sin iniciar sesión, igual que `result_unsubscribe`).

**Diseño técnico.**
- Cola idéntica a `MatchResultDelivery` y `ReportDelivery`: modelo nuevo `MatchReminderDelivery(match, user, email, kind["player"|"captain"], status, attempts, next_attempt_at, last_error, sent_at)` con `UniqueConstraint(match, user, kind)`. Es lo que garantiza que no se envíe dos veces aunque el proceso corra cada hora.
- Módulo `match/reminders.py` (calcado de `match/result_email.py`: `recipients`, `queue_*`, `due_deliveries`, `build_message`) + comando `send_match_reminders` y `JobSpec` en `backoffice/jobs.py` con `schedule="0 * * * *"` e `idle_output`. El reintento de fallos lo hace el proceso existente `send_call_reports` (se amplía para recoger también esta cola).
- Ventana: partidos con `start_date`+`start_time` (09:00 por defecto si no hay hora) entre 40 y 52 h desde ahora, hora de Madrid (`SCHEDULER_TIME_ZONE`). Solo con `Call.draft_mode=False` (convocatoria cerrada) para los jugadores; sin esa condición para el aviso al capitán.
- Preferencia: campo `UserPreference.match_reminder_email` (default True) + `UserPreference.reminder_for(user)` como `match_result_for`. Baja con token firmado (`django.core.signing`).
- Calendario: `Club.calendar_token` (CharField 32, `secrets.token_urlsafe`, único, regenerable). URL `/calendario/<token>.ics` **sin sesión** (los clientes de calendario no inician sesión), solo lectura y sin datos personales: título «Local – Visitante», fecha/hora, lugar, descripción con enlace a Zyra (que sí exige sesión). Módulo `match/calendar.py` que escribe iCalendar a mano (RFC 5545: `UID=<public_id>@zyra`, `DTSTART;TZID=Europe/Madrid`, duración por defecto 3 h, escape de `, ; \n`, plegado a 75 octetos, `SEQUENCE`/`LAST-MODIFIED` para los cambios; un partido borrado simplemente deja de aparecer en el feed). Alternativa válida: dependencia `icalendar` (revisar `pip-audit`, el repo ya audita dependencias).
- Incluir en la ventana del feed: 30 días pasados y todos los futuros. Cabeceras `Cache-Control: private, max-age=3600` y `X-Robots-Tag: noindex`.

**Reglas y casos límite.** Amistosos: se envía igual (aviso «Amistoso»). Fecha cambiada tras el aviso: la fila `Delivery` ya existe, así que no se repite; si el cambio mueve el partido a otra ventana, se crea una fila de corrección solo si cambia >24 h (campo `previous_start`). Club suspendido: no se envía (como en el aviso de resultado). Jugadores sin cuenta: no reciben nada y se avisa al capitán de «N convocados sin cuenta». Zona horaria: un partido a las 00:30 cae en el día anterior en UTC; probarlo.

**Pruebas.** `match/tests_reminders.py`: ventana de envío con y sin hora, idempotencia (dos ejecuciones = un correo), baja personal, club suspendido, convocatoria abierta, corrección por cambio de fecha; `match/tests_calendar.py`: ICS válido (parser de prueba), escapes, token incorrecto = 404, regeneración invalida el anterior, ausencia de datos personales.

**Riesgos.** Spam si falla la idempotencia (la restricción única la cubre). Los clientes de calendario sondean cada 12-24 h: avisar en la ayuda. El correo sale de `join.zyra@gmail.com` (límite diario de Gmail ~500): con crecimiento habrá que pasar a un servicio transaccional (hoy no hace falta).

**Éxito.** Porcentaje de convocados con cuenta que abren el correo no se mide (sin tracking); se mide por **ausencias de última hora** (con M3) y por suscripciones al feed (`calendar_token` consultado).

**Tamaño.** S–M · 2 PR (correo; calendario).

---

## N3 · Tarjeta de resultado en imagen y enlace público

**Problema.** El resultado se comparte hoy como texto (`share_text` en `match/views.py`). Una imagen con marca Zyra se reenvía más y es la vía de captación más barata (el pie dice «Hecho con Zyra»).

**Qué verá.**
- Botón **«Imagen del resultado»** en el enfrentamiento cerrado: PNG vertical 1080×1350 con marcador, victoria/derrota/empate, fecha, las cinco parejas con sus sets y los logos de los equipos.
- Botón **«Compartir con enlace»** (solo capitán): crea una página pública de solo lectura `/r/<token>` con la misma tarjeta, vista previa (`og:image`) al pegar el enlace en WhatsApp/Telegram, y un botón «Prueba Zyra con tu club».
- Opción por enlace: «Mostrar nombres de los jugadores» (apagada por defecto, ver riesgos) y «Desactivar enlace».

**Diseño técnico.**
- Generación con **Pillow** (ya es dependencia; fotos → WebP) en `match/result_card.py`, con las fuentes de marca (Syncopate y Archivo, ya en `static/zyra/fonts`). Función pura `render_card(match, games, show_names) -> bytes`; no toca la base de datos.
- Vista `match/<pid:match>/card.png` (con sesión) y `/r/<token>.png` (pública). Cache: `ETag` = hash del marcador y los sets; 5 minutos de caché pública.
- Modelo: `Match.share_token` (CharField, null, único) y `Match.share_names` (bool). Migración. Solo cuando `draft_mode=False`; si el acta se reabre, la página pública muestra «Acta en revisión».
- Página pública `core/templates/public_result.html`, con `<meta name="robots" content="noindex">`, sin menú, y con un freno de peticiones (`core/ratelimit.py`).
- Añadir a `docs/ai/decisions.md`: rutas públicas con token, qué datos exponen.

**Reglas y casos límite.** Amistoso: marcar «Amistoso» y no mostrar estadísticas. Rival escrito a mano: usar `rival_label`. Nombres muy largos: `Player.short_name` (ya en mayúsculas). Equipos sin logo: escudo por defecto. Idioma: según quien lo genera (es/en).

**Pruebas.** `match/tests_result_card.py`: PNG válido con dimensiones esperadas, 404 con token incorrecto o enlace desactivado, `noindex`, no aparecen nombres si `share_names=False`, el acta abierta no se publica, aislamiento entre clubes.

**Riesgos.** **Protección de datos**: nombres de personas en una URL pública. Por eso nombres apagados por defecto y revocación en un clic; añadirlo a la política de privacidad. Coste de CPU despreciable (<100 ms por render) pero con caché. Abuso por enumeración: tokens de 128 bits.

**Éxito.** Enlaces públicos creados y visitas (contador simple en la tabla) frente a registros nuevos con origen `/r/`; añadir `?ref=card` al botón de registro.

**Tamaño.** S–M · 1 PR (imagen) + 1 PR (enlace público).

---

## N4 · Disponibilidad de jugadores

**Problema.** El capitán pregunta por WhatsApp «¿quién puede?» y apunta las respuestas a mano. Es la **hipótesis H-05** del audit, sin validar (R1 en el informe `08`).

**Qué verá.**
- Al crear el enfrentamiento, cada jugador con cuenta ve en su Inicio «¿Puedes el sábado 14 contra X?» con tres botones: **Puedo**, **No puedo**, **Duda** (+ nota opcional de 60 caracteres).
- El capitán, en la pantalla de convocatoria, ve junto a cada jugador su respuesta (chips), un resumen «9 pueden · 2 dudan · 3 no pueden · 4 sin respuesta» y un filtro «Disponibles primero». También puede marcar la respuesta **en nombre de** un jugador (los que contestan por WhatsApp o no tienen cuenta).
- Aviso al convocar a alguien que dijo «No puedo».

**Diseño técnico.**
- Modelo `Availability(match, player, status["yes","no","maybe"], note, answered_by(user, SET_NULL), updated_at)` con `UniqueConstraint(match, player)`. `PublicIdModel` no hace falta (no se ve en la URL).
- Vistas POST `match/<pid:match>/availability` (miembro: su jugador; capitán: cualquier jugador del club). Reutiliza `club_match`. Formulario con `data-loading-text`.
- Integración: `match/templates/create_call.html`/`edit_call.html` y `static/js/player-selector.js` (orden y chips), tarjeta «Pendiente» en `core/templates/home.html` (miembro) y `match/phase.py` (nueva etapa informativa «Disponibilidad»).
- La convocatoria **sigue siendo del capitán** (regla 4 intacta): la disponibilidad solo informa. Se cierra al cerrar la convocatoria; luego se muestra solo lectura en el histórico.
- Aviso opcional por correo al crear el enfrentamiento (`UserPreference.availability_email`, apagada por defecto para no saturar).

**Reglas y casos límite.** Un jugador sin cuenta solo se contesta por el capitán. Cambio de respuesta tras convocar: avisa al capitán (toast al abrir la convocatoria y registro en M3). Quién ve qué: **decisión pendiente** (opción recomendada: cada miembro ve su respuesta y los totales; solo el capitán ve nombres).

**Validación previa (antes de construir).** Preguntar a 2-3 capitanes (incluido el tuyo) cuántos jugadores tienen cuenta hoy: con adopción baja, la función no aporta. Alternativa mínima: solo «marcar disponibilidad» por el capitán (sin cuentas de jugador), que ya ahorra escribirla en otro sitio. Medir tasa de respuesta a las 2 semanas.

**Pruebas.** `match/tests_availability.py`: permisos (miembro solo su jugador), unicidad, capitán en nombre de otro, club ajeno = 404, orden «disponibles primero», acta cerrada = solo lectura.

**Riesgos.** Adopción; presión social si todos ven las respuestas; notificaciones por correo en exceso. Se mitigan con el reparto de visibilidad y el correo apagado por defecto.

**Éxito.** ≥ 60 % de los jugadores con cuenta responden en las 48 h siguientes a la creación del enfrentamiento.

**Tamaño.** M · 1-2 PR.

---

## N5 · Rol de delegado

**Problema.** El capitán es un punto único: si no puede, el club se para (convocatoria, alineación y resultados son solo suyos). `informes/capitan-responsabilidades` ya describió el traspaso, pero ceder la capitanía es todo o nada y borra las credenciales SNP.

**Qué verá.** En Club › Miembros, junto a «Hacer capitán», un botón **«Hacer delegado»**. El delegado puede crear y editar convocatorias, alineaciones, resultados, advertencias y cerrar el acta; **no** puede gestionar miembros, la cuenta SNP, eliminar el club ni reabrir actas. Hasta 2 delegados por club.

**Diseño técnico.**
- `Membership.ROLES` gana `DELEGATE = "delegate"` («Delegado»). La restricción `unique_captain_per_club` no cambia. Propiedades `is_admin` (solo capitán) y nueva `can_manage_matches` (capitán o delegado).
- `core/decorators.py`: nuevo `club_manager_required` (capitán o delegado). Hoy `club_admin_required` aparece **58 veces** en vistas: hay que clasificar cada una en una tabla (en el PR) como «solo capitán» o «capitán + delegado». Propuesta: delegado en `match/views.py` (convocatoria, parejas, resultados, cierre, advertencias), `penalty/`, `players` (alta/edición de jugadores); capitán exclusivo en `core/views.py` (miembros, invitaciones, traspaso, borrar club), SNP y reabrir acta (regla 5).
- `core/services.py`: `set_role(...)`; `transfer_captaincy` y `remove_membership` deben contemplar al delegado (al traspasar, el delegado se mantiene).
- Contexto de plantillas (`core/context_processors.py`): `navigation` y botones usan `membership.can_manage_matches`.
- Correos de informe PDF: `match/notifications.py::admin_emails` incluye a delegados (configurable).

**Reglas y casos límite.** Un delegado sin jugador enlazado: permitido. Abandonar el club: igual que un miembro. `docs/ai/business-rules.md` regla 3 («un solo capitán») y 5 («solo el capitán reabre») se amplían.

**Pruebas.** Matriz de permisos (vistas × rol × club ajeno) en `core/tests_security.py` y `core/tests_roles.py`: para cada vista, capitán/delegado/miembro/anónimo/otro club. Es la prueba más importante del PR.

**Riesgos.** Regresión de seguridad por clasificar mal una de las 58 vistas: por eso la tabla en el PR y la matriz automática. Complejidad de textos («solo lectura» para miembros).

**Éxito.** Clubes con ≥ 1 delegado; acciones hechas por delegado frente a capitán en el CRM.

**Tamaño.** M · 1 PR.

---

## N6 · Notas privadas del capitán

**Problema.** El conocimiento táctico («juegan fuertes al 1 y 2», «cancelan a última hora») vive en la cabeza o en WhatsApp.

**Qué verá.** Campo «Notas» (máx. 1.000 caracteres) en la ficha del rival (`edit_team`) y en el enfrentamiento. Se muestran en el bloque «Previa» (N1) y en la pantalla de convocatoria, **solo para capitán y delegado**; los miembros no las ven. Opción de incluir las notas en el PDF de convocatoria («Notas del capitán»).

**Diseño técnico.** `Team.notes` y `Match.notes` (TextField, blank). Para amistosos con nombre escrito a mano solo hay nota en el enfrentamiento. Formularios `team/forms.py` y `match/forms.py`. Plantillas: `team/templates/edit_team.html`, enfrentamiento y convocatoria. Texto plano escapado (sin HTML ni Markdown). `match/report_pdf.py`: bloque opcional con ajuste a las 2 páginas (cuidado con `LAYOUTS` adaptativos, PR #82).

**Reglas y casos límite.** Al borrar un jugador o un equipo no se pierde nada ajeno. Se borra con el club (CASCADE).

**Pruebas.** Visibilidad por rol, límite de longitud, escape de HTML, PDF con y sin nota (caso del peor caso de dos páginas).

**Riesgos.** Pocos; si se incluye en el PDF, controlar el desbordamiento.

**Tamaño.** S · 1 PR (mejor junto con N1).

---

## N7 · Crónica automática del enfrentamiento

**Problema.** Tras el partido el capitán escribe a mano un resumen en el grupo. Con `data_analyse/sets.py` y `records.py` Zyra ya sabe qué fue notable.

**Qué verá.** Botón «Crónica» junto a «Copiar resultado»: texto de 5-8 líneas listo para pegar, p. ej.: «Victoria 8-4 contra X. La pareja 1 remontó tras perder el primer set (6-7, 6-3, 10-8). Cuarta victoria seguida del club en casa. Primer rosco de la temporada: 6-0 en el partido 4».

**Diseño técnico.** `match/chronicle.py`, función pura `build_chronicle(match, games, context) -> list[str]`. Detectores independientes y ordenados por relevancia: remontada, tie-break, super tie-break, rosco dado/recibido, racha del club, racha de una pareja, primera victoria contra ese rival (usa N1), récord (de `data_analyse/records.py`). Plantillas de frase con `gettext` y variantes para no repetir. **Determinista**: sin IA externa, sin coste ni envío de datos.

**Reglas y casos límite.** Amistoso: tono neutro y sin rachas. Empate: frase propia. Máximo 4 detectores por crónica. Si no hay nada notable, devuelve solo marcador.

**Pruebas.** Casos «dorados» (entrada → texto) por detector en `match/tests_chronicle.py`; es/en.

**Riesgos.** Texto repetitivo: tres variantes por detector. Errores de concordancia: probar con nombres de equipo reales.

**Tamaño.** S · 1 PR (mejor tras N1).

---

## N8 · Resumen de temporada («Wrapped»)

**Problema.** No hay momento de cierre ni de celebración; la retención entre temporadas depende de que el capitán vuelva en agosto.

**Qué verá.** Página `Estadísticas › Resumen de temporada` (también enlazada en el correo del cierre): balance, MVP (más victorias con mínimo de partidos), mejor pareja, mayor racha, jugador que más sube en SNP, partido más ajustado, mayor asistencia (de `data_analyse/attendance.py`) y una tarjeta compartible por jugador («Tu temporada»). Descargable como imagen con el mismo generador que N3.

**Diseño técnico.** `data_analyse/season_summary.py` que compone funciones ya existentes (`pairs`, `sets`, `records`, `attendance`, `SnpScoreHistory`); sin modelo nuevo (se calcula al vuelo; si tarda, caché por temporada). Vista `season_summary` con `?season=`. Disponible **a petición** durante la temporada («provisional») y destacada cuando el capitán pulsa «Cerrar temporada» (M4). Envío opcional a miembros reutilizando la cola de correos.

**Reglas y casos límite.** Mínimos de partidos para los premios; empates de MVP se muestran juntos; jugador dado de baja aparece con su nombre guardado (`removed_player_names`).

**Pruebas.** Temporada fixture con resultados conocidos; premios con empate; temporada vacía = estado vacío; es/en.

**Riesgos.** Que «premiar» a unos jugadores incomode: mostrar solo hechos objetivos y dejar los premios opcionales (interruptor del capitán).

**Éxito.** Compartidos de la tarjeta; regreso del club en agosto-septiembre frente a la temporada anterior.

**Tamaño.** M · 1-2 PR.

---

## N9 · Rendimiento frente a su SNP y comparador de jugadores (J5 + J6)

**Problema.** Los puntos SNP son una estimación del nivel; ver quién rinde por encima o por debajo ayuda a alinear. Es el contenido más estadístico y el de menor urgencia.

**Qué verá.** En la ficha de jugador, «Rinde por encima/por debajo de su ranking» (con intervalo y el aviso «pocos partidos»). Un comparador `Jugador A vs Jugador B`: balance, partidos juntos, rachas, SNP y evolución.

**Diseño técnico.** Rival desconocido ⇒ no hay probabilidad esperada por partido. Método posible con datos propios: regresión simple del % de victorias del club sobre los puntos SNP de la plantilla (mínimo 8 jugadores con ≥ 8 partidos) y residuo por jugador. `data_analyse/expected.py`. Comparador: vista nueva con dos selectores (reutiliza `static/js/player-selector.js`).

**Riesgos.** Mal interpretable con pocos datos: solo mostrar con mínimos y etiquetar «orientativo». Si no se alcanzan los mínimos, ocultar.

**Tamaño.** M · 1-2 PR. **Recomendación:** dejarla para después de N1-N8.

---

# B. Mejoras sobre lo existente

## M1 · Cerrar los pendientes de UX (informe `08`)

Cinco tareas pequeñas que conviene agrupar en un PR («Pulido»):

1. **Fundir «Modo» y «Tipo»** (C5). `match/forms.py::MatchForm` tiene hoy el campo `mode` (competitivo/amistoso) y `match_type` («Tipo de enfrentamiento»). Un solo selector con **Enfrentamiento · Reto · Play Off · Amistoso**, que ya coincide con `Match.MATCH_TYPES`; el JS que alterna el selector de rival (equipo vs nombre escrito) se ata al valor `amistoso`. Cuidado con el campo bloqueado «Competición» (#176) y con `Match.is_friendly`. Pruebas: `match/tests_ux.py` y la creación de amistosos con rival manual.
2. **«Repetir la última convocatoria»** (C6). Botón en `create_call.html` que preselecciona los jugadores de la última convocatoria cerrada, descartando a quien ya no está en el equipo (`Player.in_team`). Sin migración; vista de ayuda que devuelve la lista y JS que marca casillas.
3. **Advertencias con motivo y deshacer** (C7, H-07, H-35). Hoy `Penalty.reason` es texto libre (`max_length=100`) **sin traducir en la BD** (problema conocido). Cambiar a lista cerrada de motivos (código) más «Otro: texto», traducida al pintar; botón «Deshacer» en el toast durante 8 s (o «Quitar» en la ficha). Migración de datos: los textos antiguos pasan a «Otro» conservando su texto. Cierra también una de las líneas de «Problemas conocidos».
4. **Accesibilidad Q7** (H-27, H-28). `scroll-padding-top` igual a la altura de la barra (que se oculta al desplazar, PR #62); objetivos táctiles ≥ 24×24 px (WCAG 2.2 · 2.5.8) en iconos de lápiz, chips y paginación. Comprobar con axe (receta en memoria: `npm pack axe-core@4.10.2`) y ampliar `core/tests_accessibility.py`.
5. **Textos sueltos** (C4/H-01): `grep -n -i "partido" data_analyse/templates` y unificar con «Enfrentamiento» / «Partido 1-5», más `locale/en`.

**Riesgos.** El selector fundido toca el flujo más usado: probar a mano crear los cuatro tipos. **Tamaño.** M · 1-2 PR.

---

## M2 · SNP sin guardar la contraseña

**Problema.** Zyra guarda usuario y contraseña de SNP de cada capitán (cifrados con Fernet, `core/crypto.py`) y las usa con un scraper con Playwright. El aviso legal de SNP (§5) prohíbe ceder la contraseña a terceros y permite cortar el servicio (§6): el riesgo es que bloqueen cuentas de capitanes o a Zyra entera, y se romperían la actualización de puntos (lunes y miércoles) y «Completar equipo». Hay además un riesgo RGPD con los equipos del grupo (datos de personas que no usan Zyra).

**Opciones**

| Opción | Cómo | A favor | En contra |
|---|---|---|---|
| A. Pegar o subir la tabla | El capitán abre su ranking en SNP, copia la tabla (o guarda la página) y la pega en Zyra; el parser (`players/snp.py`) la convierte y entra en el mismo flujo de revisión que `snp_import` | Sin contraseñas ni scraper; implementable ya | Trabajo manual cada semana; el formato de SNP puede cambiar |
| B. Marcador (bookmarklet) | Un botón del navegador que extrae la tabla en la página de SNP y la envía a Zyra | Un clic; sin contraseña | Depende de la CSP de SNP; soporte móvil flojo |
| C. Extensión | Extensión de navegador | Mejor experiencia | Publicación en tiendas, mantenimiento |
| D. Pedir permiso a SNP por escrito | Correo ya redactado (07/10) | Mantiene todo | Sin respuesta ≠ consentimiento |

**Recomendación.** Empezar por **A como alternativa opcional** (sin retirar el scraper), con un correo mensual de recordatorio «Actualiza tus puntos» y una nota de no afiliación con SNP; migrar el resto según responda SNP. Si SNP lo prohíbe expresamente, desactivar el scraper con el interruptor `ServiceSwitch` existente.

**Diseño técnico (A).** Vista `snp_paste` (capitán) con textarea y subida de `.html`/`.csv`; parser tolerante con vista previa «Se actualizarán 18 jugadores, 2 nuevos, 1 no reconocido»; reutiliza `players/snp_service.py` y `SnpTeamImport`/`SnpScoreHistory`. Sin credenciales: la cuenta SNP deja de ser obligatoria en el alta. Comando `remind_snp_update` programado. Pruebas con HTML de ejemplo anonimizado.

**Decisión necesaria.** Cuánto riesgo asumir mientras SNP no contesta. **Tamaño.** L · 3 PR (parser + vista; alta sin credenciales; recordatorios).

---

## M3 · Registro de convocatoria estructurado

**Problema.** `CallLog.text` guarda líneas de texto separadas por «;» en español, sin traducir, y no se pueden consultar («bajas de última hora»).

**Diseño.** Modelo nuevo `CallEvent(call, kind["added","removed","closed","reopened","penalty"], player FK SET_NULL + player_name, by_user FK SET_NULL, at)`. `match/views.py::edit_call` (y cierre/reapertura) escriben eventos; la plantilla del registro compone el texto con `gettext`. Los `CallLog` antiguos se muestran tal cual (solo lectura). Migración sin backfill. Habilita: bajas de última hora (C3), fiabilidad de asistencia (C2) y la nota «cambió la disponibilidad» de N4.

**Pruebas.** Cada acción genera su evento; borrar un jugador conserva el nombre; textos es/en; el registro antiguo sigue visible. **Tamaño.** M · 1 PR.

---

## M4 · Cierre y preparación de temporada

**Problema.** Hoy «Completar equipo» lo lanza el admin a mano antes de temporada, y no hay un momento guiado para revisar plantilla, rivales y categorías. Es el pico de fricción.

**Qué verá.** En julio-agosto, una tarea en «Pendiente»: «Prepara la temporada 2026-2027». Asistente de 4 pasos: (1) revisar quién sigue en el equipo (`manage_roster` ya existe), (2) actualizar puntos y altas desde SNP (M2 opción A o scraper, respetando los límites actuales), (3) revisar rivales del grupo y divisiones (`manage_teams`), (4) ver el resumen de la temporada anterior (N8).

**Diseño.** Tarea que reutiliza la mecánica de `core/onboarding.py` (pasos que se marcan solos), sin modelo nuevo; `Club.season_prepared` (CharField) solo para ocultarla cuando se completa. Aparece automáticamente a partir del 1 de julio (la temporada va de agosto a julio, `Match.save`).

**Pruebas.** Aparición por fecha, marcado de pasos, clubes nuevos no la ven. **Tamaño.** M · 1 PR.

---

## M5 · Más razones para entrar al jugador

**Problema.** El miembro solo ve su próximo partido; su estadística está en otra pestaña.

**Qué verá.** En el Inicio del miembro con jugador enlazado, tarjeta «Mi forma»: últimos 5 partidos (✔/✘), racha, tendencia SNP (flecha y puntos) y cuántas convocatorias ha jugado. Para el capitán, enlace a «Parejas por mejorar» (R2).

**Diseño.** Compone funciones existentes de `data_analyse` (jugador) en `core/views.py::club_home`; sin modelo. **Pruebas.** Con y sin jugador enlazado, sin partidos. **Tamaño.** S.

---

## M6 · Uso en tablet

**Problema.** R4 del audit sin empezar: los anchos 768–1180 px no se han revisado, y es la tablet la que se usa en pista.

**Plan.** Capturas con Playwright (receta del repo: servidor local, `executable_path='/opt/pw-browsers/chromium'`, espera de 900 ms por las transiciones) en 768, 820, 1024 y 1180 px sobre Inicio, Enfrentamiento, Convocatoria, Alineación, Resultados y las cuatro pestañas de Estadísticas; informe con antes/después y correcciones de rejillas en `static/style.css` (secciones «Móvil: revisión general» y estadísticas `st-`). **Tamaño.** S · 1 PR.

---

# C. Plataforma y operación

## P1 · Copias programadas fuera del servidor y alerta de disco

**Situación.** `deploy/backup.sh` guarda `pg_dump` y fotos en `/opt/zyra/backups` (14 días) pero solo se ejecuta **antes de cada despliegue**. El 21/10 el disco se llenó con 31 GB de imágenes antiguas.

**Plan.**
1. Cron en el servidor (`/etc/cron.d/zyra-backup`, diario 04:30) que llame a `backup.sh`.
2. Copia **fuera** del servidor: `BACKUP_RSYNC_TARGET` ya está previsto; usar un almacenamiento barato (caja de almacenamiento o bucket) y cifrar el volcado (`age` o `gpg`) porque contiene correos y credenciales SNP cifradas.
3. **Prueba de restauración** mensual: script `deploy/restore-test.sh` que levanta Postgres temporal, restaura el último volcado, ejecuta `manage.py check` y compara recuentos de tablas clave.
4. Visibilidad en **Salud** del back-office: «Última copia hace X h» (el script escribe un fichero marca en un volumen que lee la web) y «Disco al N %» con `shutil.disk_usage`, umbrales 80/90 % y aviso por `send_staff_alerts` (el comando ya avisa de problemas nuevos).
5. Documentar en `docs/despliegue.md`. Recordatorio: la copia de `deploy.sh` en `/opt/zyra` se actualiza a mano; se podría hacer que el workflow la sincronice.

**Riesgos.** Pérdida de datos real; coste del almacenamiento externo (céntimos/mes). **Tamaño.** S · 1 PR más pasos manuales en el servidor (que no puedo hacer yo).

---

## P2 · Donación y patrocinador local

**Qué.** Etapa 1 de `informe-monetizacion.md`. Botón de donación (enlace externo en variable de entorno `DONATION_URL`; si está vacía, no aparece) en pie de la web y en «Club». Modelo `Sponsor(name, logo, url, active, club nullable)` mostrado en el pie del PDF de convocatoria (`match/report_pdf.py`, respetando las 2 páginas), en los correos y en la portada.

**Diseño.** Administración en el back-office (alta, activar/desactivar), fotos con las mismas validaciones (`core/images.py`). Migración. Los patrocinadores no se registran como imagen de otros: texto «Con el apoyo de…».

**Riesgos legales.** Un patrocinio de pago es actividad económica (IVA/autónomo); decidir antes de cobrar. Una donación voluntaria con enlace a un servicio de terceros es más simple. Añadir la nota de no afiliación con SNP. **Tamaño.** S · 1 PR.

---

## P3 · Exportar a CSV/Excel

**Qué.** Descargas para capitán y delegado: `enfrentamientos.csv` (fecha, rival, tipo, marcador, temporada), `partidos.csv` (un juego por fila con pareja y sets) y `jugadores.csv` (estadísticas por jugador y temporada). Filtros de temporada y tipo, igual que las estadísticas.

**Diseño.** Módulo `data_analyse/exports.py` con generadores en streaming; vistas `export_*` (`club_required`, solo capitán y delegado); botón en «Mi equipo» y en Estadísticas. CSV con `;`, UTF-8 con BOM y comas decimales para abrir bien en Excel en español. **Protección contra inyección de fórmulas**: prefijar con apóstrofo las celdas que empiecen por `=`, `+`, `-` o `@` (nombres de jugador y rivales vienen de usuarios). Freno de peticiones (`core/ratelimit.py`). Botón de descarga con `data-submit-download`.

**Pruebas.** Cabeceras, codificación, inyección de fórmulas, permisos, aislamiento por club, tamaño con 1.000 enfrentamientos. **Tamaño.** S · 1 PR.

---

# D. Dependencias, orden y PR

```
M3 (registro estructurado) ──► N4 (nota de cambios), C2/C3 futuros
N1 (cara a cara) ───────────► N6 (notas en la Previa), N7 (crónica: primer triunfo contra rival)
N3 (generador de imagen) ───► N8 (tarjeta del resumen)
N5 (delegado) ──────────────► P3 (quién exporta), P1 no depende
M2 (SNP sin contraseña) ────► M4 (paso 2 del asistente)
```

| Fase | PR | Contenido |
|---|---|---|
| 1 | 1 | N1 + N6 (rival, Previa y notas) |
| 1 | 2 | N2a recordatorios por correo |
| 1 | 3 | P1 copias y alerta de disco |
| 2 | 4 | N3a imagen del resultado |
| 2 | 5 | M1 pulido de UX |
| 2 | 6 | P2 donación y patrocinador |
| 3 | 7–8 | N2b calendario, N5 delegado (tras confirmar necesidad) |
| 3 | 9 | N4 disponibilidad (tras validar con capitanes) y M3 |
| 4 | 10+ | N8, M4, M2 según respuesta de SNP, N7, P3, M5, M6, N9 |

# E. Decisiones abiertas

1. **Alcance de la fase 1.** ¿N1+N6, N2a y P1 a la vez, o uno por uno?
2. **Aviso del recordatorio (N2).** Con el funcionamiento actual el capitán es quien convoca (no hay «apuntarse»), así que el recordatorio solo tiene sentido para los **convocados con cuenta**; la variante «a quien no se ha apuntado» solo existiría si se hace N4. ¿Aviso al capitán a 3 días (convocatoria sin cerrar): sí o no?
3. **Visibilidad de las respuestas (N4):** cada uno ve la suya y los totales (recomendado) o todos ven todo.
4. **Nombres en el enlace público (N3):** apagados por defecto (recomendado).
5. **SNP (M2):** ¿qué riesgo se asume mientras SNP no responde, y quieres que lo plantee primero como opción alternativa?
6. **Donación (P2):** ¿qué servicio externo prefieres para recibirla?
