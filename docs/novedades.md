# Novedades

Registro de lo que entra en `main`, de lo más reciente a lo más antiguo. Cada pull request que
añade o cambia una funcionalidad suma aquí una línea (ver [Mantener la documentación](mantener-documentacion.md)).

## 29/10/2026 · Espacios por competición (fase 1b: enfrentamientos LAPI)

- Los enfrentamientos LAPI tienen sus tipos: **Liga**, **Playoffs** y **Fase final** (los que ya existían pasan a Liga). Los de liga pueden llevar **jornada**, que sale en el listado y en el enfrentamiento.
- **Puntos de liga**: ganar 3-0 da 4, ganar 2-1 da 3 y perder 1. Se ven en cada enfrentamiento cerrado y el total de la temporada en Estadísticas › Equipo.
- En Playoffs y Fase final, la convocatoria avisa de quién no ha jugado al menos 2 enfrentamientos de liga esa temporada (reglamento LAPI) y pide marcar «Convocarlos igualmente» para incluirlos.
- El selector de jugadores de la convocatoria ya no muestra puntos SNP en LAPI.

## 28/10/2026 · Espacios por competición (fase 1a)

- Cada club es ahora el **espacio** de una competición: SNP (todos los que ya existían) o **LAPI** (3 partidos de 1 punto y 6 convocados). Una cuenta puede tener un espacio en cada competición, con un rol distinto en cada uno.
- El menú de usuario muestra la competición del espacio activo, «Cambiar de espacio» y **«Crear otro espacio»**, que abre el registro con los datos de tu equipo ya puestos. Al registrarse se elige la competición, y las divisiones son las suyas (Future…Grand Slam en SNP, 1.ª a 5.ª en LAPI).
- Las invitaciones a un espacio de otra competición se aceptan aunque ya estés en otro; a uno de la misma competición, no.
- En los espacios LAPI no se ofrece nada de SNP (cuenta, sincronización ni ese paso en «Primeros pasos»).
- En LAPI la **alineación sugerida** se basa en el historial y la afinidad de los convocados (no en puntos SNP) y funciona con 6 convocados. La pantalla de parejas no muestra puntos ni orden de juego, porque el cruce lo decide el sorteo, y el informe PDF y su correo explican el formato LAPI.
- Al crear otro espacio, si tu cuenta ya tiene jugador no se te vuelve a pedir el nombre.
- Dar de baja al último jugador de la plantilla sigue permitido, pero Zyra avisa de que te quedarás sin jugadores.
- **Varios espacios en una sola vista**: si estás en un espacio SNP y en uno LAPI, Enfrentamientos, Calendario, Inicio y Estadísticas los juntan, con el filtro **Todas · SNP · LAPI** (empieza en Todas y recuerda tu elección). Cada tarjeta lleva la etiqueta de su competición y solo muestra las acciones que tu rol permite en ese espacio. Abrir un enfrentamiento de otro espacio te cambia a él y te lo dice.
- «Nuevo enfrentamiento» dice dónde se crea o, si gestionas los dos espacios, pregunta la competición. **Rivales** tiene botón junto a «Nuevo enfrentamiento» y el formulario ofrece «¿No está el rival? Añádelo».
- Plantilla y Club: si eres capitán en un espacio y jugador en otro, solo ves el que gestionas; si eres capitán (o jugador) en los dos, cambias con un selector arriba.
- Estadísticas con «Todas»: tus partidos de todas las competiciones y una fila por equipo; los puntos y el detalle aparecen al elegir una competición.
- El informe puede **incluir datos de otras competiciones** de los convocados con cuenta enlazada (casilla en «Más opciones» al crear el enfrentamiento).
- Ya no se habla de «espacios»: el menú de usuario muestra **«Tus equipos»** (equipo, competición y tu papel en cada uno) solo para informar, y con equipos en varias competiciones la cabecera lleva tu nombre. «Cambiar de espacio» desaparece: abrir un enfrentamiento te lleva a su equipo sin avisos.
- **«Añadir equipo de otra competición»** sustituye a «Crear otro espacio»; el registro enseña desactivadas las competiciones en las que ya tienes equipo («Ya tienes Los Gladiadores en SNP») y, si ya las tienes todas, el menú lo dice.
- El selector SNP | LAPI de Plantilla, Club y Rivales aparece si gestionas los equipos de las dos competiciones o eres jugador en los dos; si eres capitán en uno y jugador en otro, ves solo el que gestionas.
- En el Inicio, si tu equipo no tiene categoría (SNP) o división (LAPI), la tarjeta lo dice.
- El Inicio con equipos en varias competiciones enseña **los dos equipos** en el banner (escudo, competición y tu papel) y «En racha» de cada uno; ya no cambia según el último enfrentamiento que abriste.
- **«Mi forma»** suma tus partidos y convocatorias de SNP y LAPI, con el desglose por competición y la competición de cada uno de tus últimos partidos. Los puntos SNP siguen igual.
- Si eres jugador en todos tus equipos, **Plantilla** sale del menú. Jugador, Parejas y Rivales ya no tienen «Todas»: se consultan por competición.
- **«Mis estadísticas»**: si juegas en equipos de varias competiciones, Estadísticas abre en una pestaña nueva con lo tuyo. «Todas» cuenta tus partidos de SNP y LAPI (sin sumar puntos) con gráficos de cada competición al lado de la otra: sets, local y visitante, partidos ganados por temporada y convocatorias en las que te apuntas. SNP o LAPI abren tu ficha en esa competición.
- Equipo, Jugador, Parejas y Rivales se consultan siempre por competición (SNP · LAPI), sin «Todas»; Equipo recuerda la que elegiste.
- En el Inicio, la tarjeta de cada equipo dice la categoría en SNP («Categoría 500») y la división en LAPI.

## 28/10/2026 · Reglas de competición en una ficha (espacios, fase 0)

- La página del enfrentamiento tiene **«Eliminar enfrentamiento»** en el menú «Más» (capitán y gestores, con el acta abierta); al cancelar vuelves a la página del enfrentamiento. Los gestores ahora también pueden eliminar enfrentamientos, y la papelera del listado se ve en rojo.
- «Guardar y cerrar acta» con resultados pendientes guarda lo que hayas puesto y te deja en «Poner resultados» con el aviso, en lugar de llevarte a la página del enfrentamiento.
- Preparación para tener más competiciones que la SNP: el número de partidos, los puntos de cada uno, los convocados mínimos y el partido de desempate salen de una ficha por competición (`core/competitions.py`) en lugar de estar fijos en el código. Para los usuarios no cambia nada: la SNP sigue con 5 partidos (3, 3, 2, 2 y 2 puntos) y 10 convocados.

## 28/10/2026 · Editar y eliminar advertencias

- El historial de **Estadísticas › Advertencias** tiene una columna **«Acciones»** con **Editar** (cambia el motivo y el detalle; el jugador y el enfrentamiento no cambian, `penalty.views.edit_penalty`) y **Eliminar** (con confirmación). Al terminar vuelves al historial con la misma temporada. Solo capitán y gestores. En móvil los botones salen en una fila bajo cada advertencia.

## 28/10/2026 · Advertencias del selector de convocatoria

- Al crear o editar una convocatoria, las advertencias que se ven junto a cada jugador son solo las de la temporada actual (antes salían todas las registradas).

## 26/10/2026 · Aviso «Añade un gestor»

- La portada muestra al capitán un aviso para que conozca el rol de gestor, con enlace a «Miembros». Se queda hasta que lo cierra con la ✕; después no vuelve a aparecer (se guarda en su cuenta, `UserPreference.manager_tip_dismissed_at`). Gestores y miembros no lo ven.
- Cuando el capitán nombra a un gestor, la primera vez que este entra en la portada ve una tarjeta «Ahora eres gestor del club» con lo que puede hacer; se queda hasta que la cierra (`Membership.manager_welcome_pending`).
## 27/10/2026 · Mi forma (gráfica SNP)

- «Mi forma» y la ficha del jugador muestran solo los partidos de la temporada actual (antes mezclaban todas) y los ordenan del más antiguo (izquierda) al más reciente (derecha), como ya hacían las estadísticas.
- Al pasar el ratón (o tocar) la gráfica de puntos SNP aparece un indicador sobre el punto más cercano con sus puntos y su fecha (`static/js/my-form-chart.js`).

- «Mi forma» reparte la tarjeta a todo el ancho: los puntos SNP tienen ahora una gráfica grande de los últimos 30 días, con fechas de inicio y hoy, máximo y mínimo y la diferencia, y el botón de la tarjeta lleva a «Mis estadísticas» en lugar de a la ficha.

## 27/10/2026 · Mi forma

- Nueva tarjeta **«Mi forma»** en el Inicio de quien tiene su cuenta enlazada a un jugador: últimos 5 partidos, racha, balance de la temporada (anillo de victorias y derrotas), de las convocatorias en las que te apuntaste a cuántas has ido, y puntos SNP. Solo cuentan los partidos competitivos. Se puede ocultar y volver a mostrar (botón «Mostrar mi forma»).

## 26/10/2026 · Pedir actualización a Zyra

- El capitán puede **pedir a Zyra que actualice su equipo desde SNP** (con una nota opcional) desde «Prepara la temporada» y desde Jugadores. El personal las gestiona en el back-office, en **Peticiones de SNP**, y al marcarlas hechas el paso de SNP de la temporada queda cumplido. Con más de cinco peticiones abiertas se avisa por correo al personal.

## 26/10/2026 · Prepara la temporada

- Del 1 de julio al 31 de octubre, el Inicio del capitán y de los gestores muestra **«Prepara la temporada»**: revisar la plantilla, actualizar desde SNP y revisar rivales y divisiones. El gestor puede hacer los pasos de plantilla y rivales; SNP, «Omitir este paso» y «Ahora no» son del capitán.
- «Completar equipo» desde la web pasa de una vez por club a **una vez por temporada** (cuenta desde el 1 de julio).
- Se corrigen los textos que aún decían «una vez al mes».

## 26/10/2026 · Rol de gestor

- Nuevo rol **Gestor**: el capitán puede nombrar hasta dos desde «Miembros» («Hacer gestor» / «Quitar gestor»). El gestor ayuda con lo deportivo: crea enfrentamientos, convocatorias, alineaciones y resultados, cierra actas, pone advertencias y gestiona jugadores y equipos. Solo el capitán sigue gestionando miembros e invitaciones, la cuenta SNP, reabrir o eliminar enfrentamientos y eliminar el club.
- Los gestores reciben también el informe PDF de la convocatoria por correo.

## 26/10/2026 · Enviar correo a usuarios desde el back-office

- Nueva sección **Enviar correo** (`/backoffice/emails/new/`): se elige el segmento (capitanes de clubes activos, capitanes de clubes sin actividad en 30 días, usuarios sin club, todos los usuarios activos o una lista de emails), una plantilla (novedades, club sin actividad, usuarios sin club, pedir opinión, mantenimiento o en blanco) y se redacta con formato. Se pueden usar `{nombre}` y `{club}`; cada persona recibe su propio correo, sin ver a las demás
- Vista previa con el primer destinatario en una pestaña nueva, «Enviarme una prueba» y envío real con casilla de confirmación (máximo 300 por envío; se omiten emails bloqueados). Queda en «Correos enviados» y en la auditoría («Correo a varios usuarios»)

## 25/10/2026 · Calendario de enfrentamientos

- Nueva vista **Calendario** en Enfrentamientos (pestañas Lista | Calendario): cuadrícula del mes con todos los enfrentamientos del club (próximos, jugados con marcador, con el acta abierta y amistosos), con navegación por meses y enlace a cada uno. En móvil se muestra como agenda por días. La ven todos los miembros y no envía ningún correo
- «Compartir resultado» genera un texto más claro para WhatsApp: cabecera en negrita con desenlace, marcador y rival, una línea por partido con su pareja y sets, y «Hecho con Zyra»

## 25/10/2026 · Cara a cara por rival y «Previa»

- Nueva pestaña **Rivales** en Estadísticas: balance contra cada equipo (jugados, ganados-empatados-perdidos, puntos y último resultado) de todas las temporadas por defecto, ordenable por rival, balance o último enfrentamiento, con buscador por nombre, paginación y filtro de temporada; sin filtro de tipo de enfrentamiento para no recargar la pantalla
- Ficha de cada rival (todas las temporadas por defecto, con filtro de tipo de enfrentamiento) con su historial paginado, el tipo de cada enfrentamiento y las mejores parejas contra él; las tablas se ajustan al ancho sin scroll lateral
- Bloque **Previa** en el enfrentamiento y al convocar: balance contra ese rival, último resultado y mejor pareja contra él (no aparece si nunca os habéis enfrentado)
- En móvil las cinco pestañas de Estadísticas caben completas (antes «Advertencias» se cortaba)

## 25/10/2026 · Cabecera en tablet horizontal

- Entre 992 y 1199 px de ancho (tablet en horizontal) la cabecera de escritorio se salía de la pantalla y la página hacía scroll lateral; ahora se compacta (menos relleno y nombre del club recortado) y cabe entera

## 25/10/2026 · Invitaciones por correo sin enlace ni WhatsApp

- En «Invitaciones pendientes» las enviadas a un correo ya no muestran el enlace copiable ni el botón de WhatsApp (se gestionan por correo; solo correo, caducidad y «Anular»). El enlace compartido sin correo mantiene copiar y WhatsApp

## 25/10/2026 · Reabrir el acta ya no reenvía el correo del resultado

- Si un acta se reabre y se vuelve a cerrar no se envía otro correo por defecto: la confirmación del recierre trae una casilla, desmarcada, «Volver a enviar el correo con los resultados» para que el capitán decida (`resend_email`; como «Resultado corregido» si el marcador cambió)
- En móvil el menú «Más» de la ficha del enfrentamiento ya no se sale por el borde izquierdo de la pantalla

## 24/10/2026 · Advertencias con motivo y «Deshacer», accesibilidad WCAG 2.2 y textos

- Las advertencias llevan un **motivo** (No se presentó, Llegó tarde, Baja de última hora, Comportamiento u Otro con detalle) en lugar del texto automático «Advertencia en el partido…», que además no se traducía. El motivo se ve en el historial de advertencias y como ayuda en el selector de convocatoria. Migración `penalty/0003`: las anteriores quedan como «Otro» con su texto escrito a mano (el automático se vacía)
- Al aplicar una advertencia, el aviso trae un botón **«Deshacer»** (15 s) y el registro de la convocatoria lista las advertencias con **«Quitar»** (`penalty.views.delete_penalty`, solo capitán)
- Accesibilidad: el lápiz «Cambiar fecha» y «Ver enfrentamiento» llegan a 24 px (WCAG 2.2 · 2.5.8); `scripts/auditoria_accesibilidad.py` mide ahora también WCAG 2.2 AA (32 páginas, escritorio y móvil, sin fallos). La página del registro de la convocatoria entra en `core.tests_accessibility`
- Textos: «enfrentamiento» donde se hablaba de la eliminatoria entera (informe PDF, aviso de amistoso, avisos de borrado y de abandono del club, registro) y «partido» solo para cada uno de los 5 partidos

## 24/10/2026 · Scripts de shell siempre con LF

- `.gitattributes` fuerza `eol=lf` en `*.sh`: la copia de `/opt/zyra/deploy.sh` guardada con CRLF desde Windows rompió el despliegue (`env: 'bash\r': No such file or directory`, código 127)

## 23/10/2026 · Gráfico «Asistencia a las convocatorias» en estadísticas del equipo

- Nueva tarjeta en «Gráficos»: % de la plantilla que se apunta a las convocatorias cerradas. Con «Todas» muestra la media de cada temporada; con una temporada, una barra por convocatoria (fecha y rival). Respeta el filtro de tipo de enfrentamiento
- Cálculo en `data_analyse/attendance.py`: apuntados / (plantilla actual que ya estaba esa temporada + quien se apuntó aunque ya no esté). No se guarda la plantilla de cada fecha, así que las bajas que no se apuntaron no cuentan

## 21/10/2026 · El despliegue limpia las imágenes antiguas

- `deploy/deploy.sh` ejecuta `docker image prune -af` cuando la web queda sana: el disco del servidor se llenó (44 imágenes acumuladas, 31 GB) y el despliegue falló con «no space left on device»

## 21/10/2026 · Puntos SNP los lunes y miércoles a las 05:00

- El «Cambio» del ranking SNP y «Quien más sube» comparan con la actualización anterior, no con la primera de la temporada (un jugador que baja y vuelve a su valor ahora marca ▲). El gráfico de puntos del jugador muestra el cambio respecto al anterior en cada punto

- `update_snp_scores` pasa de «cada noche a las 23:00 (ciclo semanal del lunes)» a lunes y miércoles a las 05:00 (hora de Madrid), porque los partidos del fin de semana tardan en verificarse en SNP. Cada ejecución es un ciclo completo (`SNP_SYNC_CYCLE`)
- Back-office → salud: una cuenta SNP cuenta como «sin sincronizar» a los 6 días (antes 8), acorde al hueco máximo de 5 días entre miércoles y lunes

## 19/10/2026 · Selector «Competición» al crear un enfrentamiento

- El formulario de nuevo enfrentamiento muestra «Competición» con SNP como única opción, bloqueada. Prepara la llegada de otras competiciones (`MatchForm.COMPETITIONS`); de momento no se guarda en el modelo, así que no hay migración

## 18/10/2026 · «Por número de partido» con tarjetas de mejor y peor partido

- Encima de las barras de «Por número de partido» (equipo y jugador) hay dos tarjetas, «Mejor partido» y «Partido más flojo» (con su %), como las tarjetas de arriba de «Sets»: así las filas de ambos paneles quedan alineadas a la misma altura
- Las barras ya no se colorean de forma especial para mejor y peor partido; lo dicen las tarjetas

## 18/10/2026 · Resultados: partido finalizado por lesión

- Nuevo check «Partido finalizado por lesión» en el formulario de resultado: permite guardar un resultado incompleto (p. ej. 7-5 / 3-0) como válido; gana quien iba ganando y el partido cuenta como victoria/derrota. Los sets parciales cuentan en las estadísticas tal cual y se muestra una marca «Lesión» (`Result.retired`)

## 18/10/2026 · «Por número de partido» alineado con «Sets»

- Las barras del panel «Por número de partido» (equipo y jugador) arrancan justo bajo la descripción, con la misma altura de fila y espaciado que «Sets», y se reparten la altura del panel sin hueco vacío arriba
- Se quita la frase bajo el gráfico («Mejor en el partido 2… y peor en el partido 1…»); el mejor y el peor partido siguen marcados con color

## 18/10/2026 · Correos de Zyra legibles en el modo oscuro del móvil

- Los correos usan el verde lima de la app con texto negro (cabecera del resultado, cabecera de la tabla) y un pie claro con texto y logo negros: el modo oscuro de Gmail invertía solo parte de los colores y el texto lima quedaba casi invisible; con texto negro el contraste se mantiene en modo claro y oscuro

## 18/10/2026 · El capitán recibe el aviso del resultado y envío manual desde el back-office

- El capitán que cierra el acta ya recibe también el correo del resultado (antes quedaba excluido)
- Back-office → ficha del club → «Enviar el resultado de un enfrentamiento»: se elige un enfrentamiento cerrado del club y se reenvía el aviso a sus miembros (respetando la baja de cada cuenta y sin enviar si el club está suspendido); queda en la auditoría («Aviso de resultado reenviado») y en el panel de «Salud de los servicios»

## 18/10/2026 · Top 5 solo con datos favorables

- «Mejores parejas» y «Mejores jugadores» (local y visitante) en estadísticas por equipo ya no muestran a quien tiene 0 % de victorias aunque llegue al mínimo de partidos (antes salía una pareja con 0V-2D); si nadie cumple, el panel dice «No hay ninguna pareja con datos favorables que mostrar»
- «Parejas destacadas» (mejores) tampoco incluye parejas sin victorias

## 18/10/2026 · Aviso por email del resultado al cerrar el acta

- Al cerrar el acta de un enfrentamiento, cada miembro del club recibe un correo con el marcador, el resultado de las cinco parejas y su propio partido resaltado si jugó; hay diseño de victoria, derrota, empate y amistoso (que avisa de que no cuenta en las estadísticas competitivas)
- El capitán, que cierra el acta, también lo recibe. Si se reabre y se cierra con el mismo marcador no se repite; con otro, llega «Resultado corregido»
- Se desactiva desde «Mi perfil» (interruptor «Aviso del resultado por email») o con el enlace de baja del propio correo
- Back-office → «Salud de los servicios»: panel de avisos de resultado (enviados, fallidos, pendientes, último envío y lista de problemas); los fallidos suben a la bandeja de atención, a las alertas por email y al resumen semanal
- Si el envío falla, el acta queda cerrada y `send_call_reports` lo reintenta (2, 10, 30 y 120 min)
- Migraciones `core/0020` y `match/0013`
- Arreglo: el catálogo inglés tenía dos entradas repetidas («fuera del equipo» y un aviso de «Completar equipo») que impedían compilarlo

## 18/10/2026 · Estadísticas: «Por número de partido» sin texto explicativo

- El panel «Por número de partido» (estadísticas de equipo y de jugador) ya no lleva la nota «% de victorias en cada partido…»: título, barras y la frase de mejor/peor partido bastan y se gana espacio

## 18/10/2026 · Estadísticas: «Por número de partido» más limpio y centrado

- La nota del panel «Por número de partido» ya no explica quién juega el partido 1 («el partido 1 lo juega la pareja que más suma»); en jugador queda «% de victorias en cada partido del enfrentamiento.»
- Las barras quedan centradas verticalmente en el panel cuando la tarjeta es más alta que su contenido

## 17/10/2026 · Sin doble clic en ningún formulario

- Todos los formularios de la web que envían datos (equipos, jugadores, enfrentamientos, convocatorias, invitaciones, cuenta, back-office…) se bloquean al enviarse: el botón pulsado se deshabilita y muestra un indicador con el texto de la acción («Guardando el equipo…», «Enviando la invitación…», «Cerrando el acta…»), y un segundo clic o Intro se descarta
- Solo se bloquea tras un envío válido: si el navegador o la página detectan un error, el botón sigue activo; al volver con «Atrás» se desbloquea y, si la respuesta no cambia de página (exportar CSV), a los pocos segundos
- Los lectores de pantalla oyen el mismo texto (`aria-busy` y un aviso `role="status"`)
- La comprobación de nombres parecidos al crear equipos y jugadores, y el botón de ver la contraseña SNP, también ignoran el doble clic
- Un formulario nuevo declara su texto con `data-loading-text`; `core.tests_submit_lock` falla si falta o no está traducido

## 17/10/2026 · El capitán sabe qué le toca

- La tarjeta «Registrarme como capitán», el formulario «Registrar un club» y «Primeros pasos» explican que el capitán invita a los jugadores, crea los equipos y apunta los resultados, y que puede traspasar la capitanía a otro miembro
- La nota de «Miembros» describe el traspaso paso a paso («Hacer capitán»: el anterior capitán pasa a miembro de solo lectura)

## 17/10/2026 · Registro: usuario repetido sin error 500

- El usuario (que sirve para iniciar sesión junto al email) sigue siendo único sin distinguir mayúsculas; si dos envíos coinciden y la base de datos rechaza el duplicado, el registro (por invitación, de club o de cuenta) muestra «Ya existe un usuario con ese nombre» en el formulario en vez de un error 500
- El email es único también en la base de datos (índice sobre el email en minúsculas; migración `core/0019`, que se detiene con la lista de emails repetidos si ya los hubiera)
- Los formularios de registro (invitación, club y cuenta) bloquean el botón al enviar y muestran «Creando tu usuario…» con un indicador, para que un doble clic no envíe dos veces (`static/js/submit-lock.js`)

## 17/10/2026 · Back-office: jugador enlazado en la ficha de usuario

- La tarjeta «Cuenta» de la ficha de usuario muestra el jugador (y equipo/club) al que está enlazada la cuenta, o «Sin enlazar»

## 16/10/2026 · Gráficos sin datos y barras juntas

- Estadísticas de equipo, «Enfrentamientos ganados por año»: en escritorio las barras de ganados, empatados y perdidos de una misma temporada van pegadas, como en el móvil (se limita el ancho del grupo y no el de cada barra) y cada temporada lleva una banda tenue detrás para ver qué barras son suyas, también en el móvil
- «Juegos como local», «Juegos como visitante», «Enfrentamientos ganados por año», «Balance de partidos por jugador» y los gráficos por temporada de jugador muestran «No hay datos todavía.» en vez de un gráfico vacío

## 16/10/2026 · Protección contra inundaciones de peticiones

- Freno general por IP (`FloodProtectionMiddleware`): 240 GET y 60 POST por minuto y proceso (`FLOOD_LIMIT_GET_PER_MINUTE`, `FLOOD_LIMIT_POST_PER_MINUTE`), con respuesta 429; `/healthz/` y estáticos exentos
- Límites por usuario en el PDF de convocatoria, el reenvío del informe y «Completar equipo»
- Gunicorn con hilos, reciclado de workers y límite de línea de petición; Caddy con tiempos máximos de cabecera/cuerpo y cuerpo de 12 MB; `DATA_UPLOAD_MAX_MEMORY_SIZE` de 2 MB

## 16/10/2026 · Error de nacionalidad en SNP y gráfico móvil de temporadas

- «Sincronizar datos» / «Completar equipo»: si SNP no muestra el menú «Series Nacionales» del país configurado, el mensaje dice que lo más probable es que la nacionalidad del equipo (donde disputa la competición) no sea la correcta, y la pantalla de bienvenida y la tarjeta de Inicio ofrecen «Editar mi equipo» (`SnpScrapeError.TEAM`; `sync_task` devuelve `team_fix_url`). El resto de errores no cambia
- Estadísticas de equipo, «Enfrentamientos ganados por año»: barras agrupadas por temporada con la etiqueta horizontal debajo (en el móvil «24-25», «en curso» en una segunda línea), número encima de cada barra y leyenda compacta arriba

## 15/10/2026 · Primer uso sin fricción (informe de usabilidad)

- Registro del club **en 3 pasos** (club → cuenta → jugador) con barra de progreso, borrador entre pasos y vista correcta en el móvil; validación al salir de cada campo, resumen «Faltan N campos» y foco en el primer error (`register-wizard.js`, `form-errors.js`, que además enlaza cada error con su campo con `aria-invalid`/`aria-describedby`)
- Categoría y nacionalidad del equipo vienen como Masculino y España; SNP viene preseleccionado y el aviso de coincidencia exacta queda plegado bajo la opción manual; ayudas con ejemplos en categoría, nacionalidad y división
- Aviso a quien se registra como jugador de que necesita la invitación de su capitán
- Inicio: «Primeros pasos» (conectar SNP o añadir jugadores → invitar → primer enfrentamiento) va primero, con un solo botón «Siguiente paso» y sin los bloques vacíos mientras queden pasos; aviso único de email por confirmar con «Reenviar» y «Cambiar email»
- «Completar equipo» ya no tiene botón en Jugadores: en la portada del capitán queda la tarea «Sincronizar datos» hasta que salga bien (pendiente, en curso con «Ver progreso» y «Cancelar», o error con «Reintentar»; explica la espera o el bloqueo). Cancelar o corregir la cuenta SNP ya no bloquea el reintento, y la pantalla de espera avisa si tarda y deja seguir en Inicio. Casillas, radios e interruptores de Preferencias sin solaparse con su texto. Mientras sincroniza, una barra de progreso por pasos (sesión iniciada, equipo abierto, jugadores leídos…) se ve en toda la web sin bloquear la navegación, se impide crear jugadores, equipos y enfrentamientos hasta que termine, y la búsqueda arranca al momento en vez de esperar al minuto. Pausa de 1 minuto tras un error; si SNP rechazó la cuenta no se relanza hasta cambiar usuario o contraseña; la tarea «Conecta SNP o añade a tus jugadores» no se da por hecha si falla; un fallo al avisar al personal ya no tapa el motivo real; las horas se muestran en hora de Madrid
- Tras aceptar una invitación, bienvenida de una pantalla con el capitán, el equipo y la próxima convocatoria, y paso directo a elegir el jugador
- Club: accesos rápidos (invitar, crear rival, nuevo jugador, crear enfrentamiento), estado de cada tarjeta con enlace, leyenda club/equipo/grupo y «Zona de peligro» para abandonar el club
- Crear enfrentamiento: un solo selector «Tipo de enfrentamiento» (incluye Amistoso) y enlace «Crear rival» cuando no hay rivales; la barra inferior se esconde al escribir en un campo
- Estadísticas sin enfrentamientos cerrados: una tarjeta «Cierra tu primer enfrentamiento y verás esto» con vista previa de ejemplo, sin pestañas ni filtros
- Estados vacíos con verbo de acción; textos «partido» → «enfrentamiento» donde se refieren al cruce de equipos
- Email de «Mi perfil» en línea completa con los botones debajo; invitaciones con una línea y «Más información»
- Objetivos táctiles de al menos 24 px y `scroll-padding` bajo la cabecera fija

## 15/10/2026 · Mejoras de usabilidad de la auditoría UX

- Vocabulario: «Enfrentamiento» (cruce de dos equipos) y «Partido 1-5» (cada pareja); «Alinear parejas» sustituye a «Crear partidos»
- Nueva sección **Club** en el menú (Miembros e invitaciones, Mi equipo, Rivales, Cuenta SNP); el menú de cuenta queda con Mi perfil, idioma y Cerrar sesión; la barra móvil sigue el mismo orden con etiquetas
- Inicio del capitán con bloque «Pendiente» (una fila por enfrentamiento abierto con su siguiente acción) y «Todo al día»; el miembro ve si está convocado y su pareja
- Página del enfrentamiento con indicador de fases, un botón primario «Siguiente: …», menú «Más» y resumen Victoria/Derrota; al cerrar el acta se queda en el enfrentamiento con «Compartir resultado» y aviso si la fecha es futura
- «Resultados del enfrentamiento»: los 5 partidos en una pantalla con validación en vivo, «Guardar» y «Guardar y cerrar acta»
- Crear enfrentamiento: tipo único, rival con casa/fuera, hora y lugar, `novalidate` con errores bajo cada campo
- Las convocatorias exigen un mínimo de 10 jugadores
- Selector de convocatoria: SNP, «Jugó N de M», ordenado por SNP, 30 sin paginar
- Estadísticas del equipo: en escritorio, panel lateral «En esta página» que marca la sección visible; en móvil, índice de secciones, sin gráfico circular, barras por temporada con «en curso»
- Temporada por defecto común (temporada actual, «Todas» a un toque y se recuerda en la sesión)
- Ficha del jugador con pestañas Resumen / Estadísticas y forma reciente; «Estadísticas › Jugador» busca y abre la ficha
- «Peores parejas» pasa a «Parejas por mejorar» (mínimo 4 partidos); puntos SNP y fechas con formato común
- Mi perfil: cambiar el email pide la contraseña; el informe de convocatoria solo lo ve el capitán; botón propio «Subir foto»
- Eslogan en castellano «Sube el nivel de tu equipo»
- Inicio: «Ver estadísticas» del jugador en racha también para los miembros; si varios empatan a racha, se muestra uno distinto cada día

## 15/10/2026 · Estadísticas solo con partidos cerrados

- Ninguna estadística (jugador, pareja, afinidad, convocatorias, informe mensual ni informe PDF) cuenta ya partidos con el acta abierta, aunque alguno de sus partidos individuales estuviera cerrado
- El aro de «% de victorias» se lee bien con el 100 %
- El listado de equipos muestra 6 por página
- Estadísticas por jugador con una temporada concreta: se ocultan «Partidos jugados» y «Evolución del % de victorias» (solo tienen sentido con todas las temporadas); se mantienen los puntos SNP y el listado de partidos

## 14/10/2026 · Estadísticas: un toque en el móvil ya no abre un partido

- La fila de las tablas de partidos (jugador y pareja) ya no usa un enlace estirado con `::after`: en algunos Safari el enlace no se quedaba dentro de su fila y cubría toda la página, así que cualquier toque (temporadas, «Todas», selectores) abría un partido. Ahora `a11y.js` abre el enlace de la fila al pulsarla

## 14/10/2026 · Selectores con buscador en el móvil

- Al elegir una opción del buscador (`player-picker.js`) se descartan durante 600 ms los clics siguientes (clic emulado del móvil o doble toque), para que ninguno caiga sobre el enlace de un partido de la tabla
- Elegir una temporada (o un jugador) en el buscador ya no abre el partido que había debajo: la opción se elige en `click` y no en `mousedown`, así el click emulado del móvil no cae sobre el enlace de debajo (`player-picker.js`, también el autocompletado SQL del back-office)

## 14/10/2026 · Logo de Zyra en los resultados de Google

- `/favicon.ico` responde 200 en la raíz (antes daba 404) y la cabecera enlaza iconos PNG de 48, 96 y 192 px (múltiplos de 48 que pide Google) generados desde `favicon.svg`; el SVG ya no es el primero de la lista
- Google tarda días o semanas en actualizar el icono: tras desplegar, pedir la reindexación de la portada en Search Console

## 14/10/2026 · Estadísticas de jugador más simples

- Al elegir una temporada, el panel «Temporada» solo conserva el listado de partidos jugados; el resto ya se ve en el resumen superior, que sigue el filtro de temporada
- Nueva tarjeta «Puntos ganados» junto a «Mejor racha», y «Local y visitante» añade los juegos ganados y perdidos, con leyenda de colores y «No hay resultados para mostrar» cuando no hay partidos

## 14/10/2026 · Temporada de incorporación como selector

- Jugador (crear y editar): «Temporada en la que se unió» pasa de texto libre a un selector con búsqueda que solo admite temporadas de la lista (2015-2016 hasta la actual, sin temporadas futuras, más las pasadas que ya existan en el club); un valor antiguo fuera de la lista se conserva al editar
- Estadísticas · Jugador: «Apuntado y alineado» y «Se apunta a las convocatorias» (y su desglose por temporada) solo cuentan desde la temporada de incorporación; sin ella se cuenta todo
- Estadísticas · Jugador: los chips de temporada no ofrecen las anteriores a su incorporación (salvo que haya jugado en ellas)
- Fuente Syncopate: las tildes y la Ñ de los títulos (p. ej. RODRÍGUEZ) se ven más pequeñas y separadas de la letra
- Informe mensual del jugador: no lista como «No apuntado» las convocatorias anteriores a su incorporación

## 14/10/2026 · Interruptor de jugadores en el listado

- El listado de jugadores tiene el interruptor «Mostrar solo jugadores de mi equipo» (marcado por defecto, solo capitanes), igual que el de equipos; al desmarcarlo se ven también los que ya no están en el equipo

## 14/10/2026 · Imagen para compartir: el logo

- Al compartir el enlace de Zyra (WhatsApp, Telegram, X…) la tarjeta muestra solo el logo sobre fondo oscuro (`og-image-v2.png`; el nombre nuevo evita la caché de WhatsApp y Facebook)

## 14/10/2026 · SEO: guías, imagen para compartir y «Hecho con Zyra»

- Nueva sección pública `/guia/` con tres guías para capitanes (organizar parejas, puntos SNP y plantilla de convocatoria), en español e inglés, con sitemap, hreflang y datos estructurados; enlazada desde la portada y el pie
- Plantilla de convocatoria en PDF descargable sin registro (`/guia/plantilla-convocatoria-padel.pdf`)
- Imagen para compartir de 1200×630 (`og-image.png`) y `twitter:card=summary_large_image`
- Pie «Hecho con Zyra · dominio» (con enlace) en el informe de convocatoria, el informe mensual y los correos
- `/BingSiteAuth.xml` en la raíz para verificar el dominio en Bing Webmaster Tools

## 14/10/2026 · Tarjetas de sets legibles

- Estadísticas · Jugador: «Apuntado y alineado» muestra también a cuántas convocatorias cerradas se apunta y a cuántas no, con los mismos filtros (temporada y tipo de partido)
- Estadísticas · Jugador: «Partidos y sets» en dos filas (Por número de partido y Sets clutch; debajo Apuntado y alineado)
- Estadísticas · Sets: las tarjetas (Set decisivo, Tie-breaks, Remontadas…) ponen título y porcentaje arriba, barra y descripción a ancho completo debajo (sin caja), sin recortes en móvil; lo mismo en «Local y visitante» (jugador y pareja) y «Apuntado y alineado»

## 14/10/2026 · Fecha editable

- Partidos: la tarjeta del listado muestra «Pdt. cerrar acta» cuando todos los partidos del acta abierta ya tienen resultado (y «Sin resultado» mientras falte alguno)
- Partidos: se puede cambiar la fecha de un partido creado (lápiz junto a la fecha, solo con el acta abierta); la temporada se recalcula

## 14/10/2026 · Contraseña para cuentas de Google

- Las cuentas creadas con Google ven en «Mi perfil» el botón «Añadir contraseña» (sin pedir la actual, con la lista de requisitos en vivo y el ojo para mostrarla) y así pueden entrar también con usuario o email; el acceso con Google sigue funcionando
- «Mi perfil» muestra en «Cuenta» el correo electrónico, el nombre de perfil (usuario, solo lectura) y la contraseña

## 14/10/2026 · Traspaso de capitanía y cuenta SNP

- Al traspasar la capitanía se borran las credenciales SNP guardadas y el nuevo capitán ve de nuevo «Primeros pasos» con la tarea «Registra tu cuenta de SNP» (que ahora forma parte de la lista)
- Las confirmaciones (traspasar capitanía, quitar miembro, borrar cuenta SNP, reabrir acta y las del back-office) salen en un popup de Zyra (`data-confirm` + `confirm-modal.js`) en vez del diálogo del navegador

## 13/10/2026 · Reto y Play Off sin empate

- En partidos de Reto y Play Off no hay empate: si la eliminatoria queda 6-6 al cerrar el acta, gana quien ganó el partido 3; el resto de tipos sigue admitiendo empate
- Estadísticas de equipo: nueva tarjeta «Eliminatorias 6-6» con el porcentaje (y barra) de las que cayeron a favor y en contra (respeta el filtro de temporada y tipo)
- En la tarjeta de un Reto o Play Off cerrado 6-6 se indica que la pareja 3 ganó (o perdió) su partido y desempató para entender de un vistazo por qué consta como ganado o perdido

## 13/10/2026 · Cuentas sin club

- El registro empieza con un panel para elegir «Registrarme como jugador» (cuenta sin club) o «Registrarme como capitán» (crear club); la portada y el menú apuntan a él
- Nueva opción «Solo quiero unirme a un club por invitación» en el registro (también con Google): crea la cuenta sin club y la deja en una página de espera que explica cómo unirse con una invitación o registrar un club
- Back-office: «Sin club» en el dashboard cuenta las cuentas activas que esperan invitación (con las de más de 7 días y su evolución diaria), el filtro de usuarios las lista de la más antigua a la más reciente y el informe de uso añade las cuentas nuevas con y sin club
- Migración `backoffice` 0005 (`DailyMetric.users_without_club`)

## 13/10/2026 · «Entrar como» con edición

- Con «Entrar como» el personal ya puede crear y corregir datos como el usuario para resolver incidencias sin pasar por la consola SQL: banner «Editando como…», motivo obligatorio, 30 minutos y cada cambio (POST/PUT/PATCH/DELETE) anotado en la auditoría como `impersonate.write` a nombre del personal real. Siguen bloqueados el perfil/cuenta (email, contraseña), abandonar o borrar el club y ver la clave de SNP

## 13/10/2026 · Back-office: salida a la web siempre visible

- El menú lateral del back-office se desplaza por su cuenta y «Volver a la web» queda fijo al pie, así que ya no se pierde en pantallas bajas; en móvil el pie envuelve en varias líneas

## 13/10/2026 · Datos de partida en producción

- La imagen incluye `populate_db.py` y `populate/` para cargar los datos de partida en el servidor (PR #137); `populate_db.py` guarda ahora los puntos como `7/5`, verifica el email del capitán en allauth (para «Entrar con Google»), conserva las cuentas que ya existan (solo exige que no haya clubes) y crea el capitán como usuario normal (`--superusuario` para el comportamiento anterior)
- `backup.sh` ya no crea el volumen de fotos si no existe (lo creaba root y la web no podía escribir)

## 13/10/2026 · Despliegue: llave SSH más tolerante

- `DEPLOY_SSH_KEY` acepta la llave en texto o en base64 de una línea, y el workflow la valida antes de conectar (PR #136)

## 13/10/2026 · Despliegue: espera a la base de datos

- `deploy.sh` espera a que PostgreSQL esté sana antes de la copia de seguridad (PR #135; el primer despliegue fallaba porque la base de datos aún se estaba creando)

## 13/10/2026 · Configuración de despliegue con Docker

- Imagen Docker única (web y lanzador), `docker-compose.yml` con PostgreSQL, Caddy (https y fotos), scripts de despliegue y copia de seguridad, y workflow `deploy.yml` que publica la imagen en GHCR; el despliegue por SSH queda apagado hasta tener servidor (PR #134)
- Estáticos de producción con WhiteNoise (con hash en el nombre); el correo de contacto de los avisos sale de `CONTACT_EMAIL` y el remitente técnico de `ZYRA_SENDER`
- Guía de despliegue en `docs/despliegue.md`

## 13/10/2026 · Equipos: interruptor del grupo

- «Mostrar solo equipos de mi grupo» (Equipos) es ahora un interruptor propio (`.z-toggle`) con los colores de Zyra, en vez de una casilla desencajada

## 13/10/2026 · «Completar equipo» una sola vez y edición desde el back-office

- Listado de equipos: casilla «Mostrar solo equipos de mi grupo», marcada por defecto; el capitán puede desmarcarla para ver todos los equipos del club
- «Completar equipo» desde la web solo se ofrece una vez (en el registro o tras registrar la cuenta SNP). Si falla se muestran los errores habituales (idioma, nombre del equipo, cuenta); tras 3 fallos se oculta, se avisa al capitán de que se ha notificado al administrador y se avisa al personal por email y auditoría. Después solo lo lanzan el back-office o el proceso automático
- Back-office: el personal puede editar equipos, jugadores y la cuenta SNP de un club desde su ficha (con las mismas reglas que el capitán) y reponer la opción de la web; todo queda en la auditoría con el valor anterior y el nuevo. «Entrar como» sigue siendo de solo lectura

## 12/10/2026 · Back-office: operación, auditoría y «Entrar como»

- Procesos: el aviso «El lanzador de procesos no está en marcha» se basa ahora en un latido real del lanzador (`SchedulerState`) y en procesos atrasados; las ejecuciones sin nada que hacer ya no llenan el historial; los correos de fallo no se repiten (primero, recordatorio cada 6 h y aviso de recuperación); `run_scheduler --loop`; «Ejecutar ahora» pasa por el lanzador si está vivo; los ids de equipo aceptan `TEA…`
- Nuevos procesos: limpieza (`purge_backoffice_data`), resumen diario, avisos al personal, resumen semanal y envío por correo de consultas SQL guardadas
- Registro de auditoría de las acciones del personal y registro de correos enviados
- Consola SQL más estricta (bloqueos, columnas protegidas, rol de solo lectura opcional) y CSV a prueba de inyección de fórmulas
- Métricas: activos reales por día (DAU/WAU/MAU), tendencia de 30 días, «Qué atender» en el dashboard, contadores en el menú, errores 500 y peticiones lentas con su ruta, embudo de clubes
- Usabilidad: buscador global, menú agrupado, ficha de club con seguimiento (etapa, contacto, notas, tareas), correo a capitanes con plantillas, renombrar/eliminar club, traspasar capitanía, restablecer contraseña y reenviar confirmación
- «Entrar como» un usuario (solo lectura, 30 minutos, con motivo y auditado) para ver lo que ve el capitán

## 12/10/2026 · Desplegables propios

- Todos los selectores desplegables (tipo de partido, equipos, categoría, filtros del back-office…) usan un desplegable propio de Zyra, con fondo oscuro y acento lima, en vez del del navegador. Funciona con teclado (flechas, Enter, Esc, escribir para saltar) y en móvil; el `<select>` original sigue enviándose con el formulario
- Desplegables: la lista se abre ahora justo bajo su selector aunque la página esté dentro de un panel con efectos (se colgaba de un contenedor y salía desplazada)

## 12/10/2026 · Seguridad y cuentas

- Back-office › «Emails sin confirmar»: lista las cuentas cuyo email no se ha confirmado (con la fecha de registro), permite enviarles un aviso con el enlace de confirmación y un plazo (7 días por defecto, `UNVERIFIED_ACCOUNT_DEADLINE_DAYS`) y eliminar la cuenta una vez vencido el plazo, escribiendo su usuario. Cada aviso y eliminación queda en `AccountNoticeLog` con fecha y quién lo hizo
- Seguridad: Django 5.2 LTS y Pillow 12.3; frenos de abuso (login, registro, invitaciones, contraseña) en caché compartida con la IP real; verificación de email con enlace (y protección frente a tomar una cuenta no verificada vía Google); ruta del admin obligatoria en producción; Bootstrap, Font Awesome y Chart.js servidos desde `static/vendor/`; `pip-audit` en CI
- Cuentas: un único capitán por club con «Hacer capitán» (solo a jugadores enlazados) y «Eliminar mi cuenta» en «Mi perfil»
- Actas: se pueden reabrir desde la convocatoria y el cierre es atómico; los resultados se guardan con valores estándar
- SNP: «Completar equipo» se encola y lo procesa un trabajo aparte; el límite se quita por club desde el back-office (ya no por nombre); nuevo apartado «Servicios» para apagar SNP y aviso por email si cae
- La temporada empieza el 1 de agosto; la validación automática de fotos con AWS queda apagada; política de privacidad actualizada

## 12/10/2026

- SNP: «Competiciones/Competencias» se abre justo después de elegir el país (antes de «Mis equipos»). El proceso `add_group_teams` ya no lee jugadores: solo entra en Competiciones y lee la clasificación. En el registro y «Completar equipo» la clasificación se lee antes de los jugadores
- Informe mensual: el PDF pasa a 2 páginas e incluye las convocatorias del mes (a cuántas te apuntaste, en cuáles fuiste convocado, en cuáles no y a las que no te apuntaste, con el listado), una gráfica de la evolución de tus puntos SNP durante el mes y el panel «Sets clutch» de las estadísticas del jugador (set decisivo, tie-breaks, remontadas, cerrar el partido, sets ajustados y super tie-break)
- Backoffice › proceso «send_monthly_reports»: nuevas opciones «Mes» y «Enviar solo a este email» para mandar el PDF a mano a una cuenta aunque ya lo haya recibido ese mes (también si desactivó los correos). Queda anotado en `MonthlyReportDelivery` (`manual_sends`, `last_manual_at`) y en el registro de la ejecución
- Back-office: nuevo proceso manual «add_group_teams» que pide el id del equipo propio de un club (TEA...) y crea solo los equipos del grupo que SNP muestra en su clasificación (sin tocar jugadores ni aplicar los límites de la web). También existe `--dry-run` desde la línea de comandos
- Tipografía: corregido el hueco que aparecía en el título «ZYRA» («ZY RA») con la fuente en cursiva; la cursiva de Syncopate Bold se regenera con los espaciados de cada letra bien calculados
- Estadísticas › Jugador y › Parejas: selector de temporadas (Todas, las tres últimas y buscador) como en el equipo; se combina con el tipo de partido y se mantiene al navegar
- Tipografía: los títulos de toda la web, los PDF (convocatoria e informe mensual), la documentación y los emails usan la misma fuente, Syncopate Bold en cursiva (antes los PDF la llevaban sin cursiva). Se añade `Syncopate-BoldItalic.ttf`, una versión oblicua de la fuente (licencia libre) para que la cursiva sea idéntica en todos los sitios
- Registro con SNP y «Completar equipo»: además de los jugadores, el scraper entra en «Competiciones/Competencias», lee la tabla «Clasificación» y crea los equipos del grupo que aún no existen (con la categoría, nacionalidad y división del equipo propio). No duplica equipos con el mismo nombre o muy parecido, da de alta en el grupo los que ya existían fuera y, si el club no tuviera equipo propio, marca como tal el que SNP resalta en negrita. Si este paso falla, los jugadores se importan igual
- Equipos: «Gestionar equipos» muestra también los equipos dados de baja del grupo (filtro «Fuera de grupo») para volver a darlos de alta. Al crear un equipo, el aviso de nombre parecido incluye los dados de baja y ofrece «Dar de alta de nuevo» en vez de duplicarlo. El equipo propio ya no puede darse de baja del grupo (y los que lo estaban vuelven a estarlo)
- Jugadores: el buscador del listado funciona igual que el de las convocatorias: filtra en vivo mientras escribes (sin recargar la página), ignora mayúsculas y tildes y busca en el nombre completo. La paginación (9 por página) también es inmediata
- Partidos: filtro por tipo de partido (Todos, Competitivos, Amistosos y, dentro de Competitivos, enfrentamientos, retos o play offs), con los mismos chips que las estadísticas. Se combina con la temporada, el rival y el buscador, y se mantiene al paginar
- Informe mensual por email: cada jugador con cuenta enlazada recibe el día 1 un PDF con sus estadísticas del mes anterior (partidos, victorias, sets, parejas y detalle). En «Mi perfil» se activa o desactiva y se elige si cuentan todos los partidos o solo los competitivos, y el correo incluye un enlace para desactivarlo sin iniciar sesión. Comando `send_monthly_reports` (idempotente, no repite un mes ya enviado)
- Crear partido: nuevo selector «Datos del informe PDF» (todos los datos o solo partidos competitivos). Con «solo competitivos» el informe de la convocatoria (rendimiento, rachas, forma, Jug./Conv., último, balance y precedentes) deja fuera los amistosos. Bajo el selector, «Edita tus preferencias» lleva a «Mi perfil», donde se guarda la opción por defecto de la cuenta

## 10/10/2026

- Informe PDF de convocatoria: la columna «Jug./Conv.» no cuenta la convocatoria ni el partido actuales (lo explica una nota bajo la tabla) y se redistribuyen las columnas para que los puntos SNP y los registros no salten de línea
- Partidos: al crear un partido se abre directamente su página (para hacer la convocatoria) en vez de volver al listado
- Portada: «Volver arriba» sube hasta el principio de la página (antes se quedaba bajo la cabecera) y en móvil ya no se repite el botón de registro al final

## 09/10/2026

- Documentación para asistentes de IA: el índice `ZYRA_CONTEXT.md` se consulta con una búsqueda por palabra (columna de claves con sinónimos en español e inglés), cubre también la portada, la plantilla base, los estilos y los JS de cada pantalla, trae recetas de qué tocar según el tipo de cambio, y el CI comprueba que esté al día (`scripts/check_ai_docs.py`)
- Portada: al final, en ordenador, el botón «Volver arriba» sustituye al segundo «Registrar mi club gratis»
- Documentación para asistentes de IA: índice `ZYRA_CONTEXT.md` en la raíz, `CLAUDE.md` y `docs/ai/` (arquitectura, modelo de datos, reglas de negocio, comandos y decisiones), para retomar tareas sin recorrer todo el código
- Accesibilidad: texto alternativo en fotos, escudos y logos, gráficos descritos para lectores de pantalla, encabezados sin saltos de nivel, título propio en cada página, enlace «Saltar al contenido», etiquetas en todos los campos, iconos decorativos ocultos, más contraste en botones de borrar y jugadores fuera del equipo, tablas desplazables con el teclado y pruebas automáticas en CI (`core/tests_accessibility.py`) más auditoría con axe-core (`scripts/auditoria_accesibilidad.py`)
- Posicionamiento en buscadores: portada con más contenido (qué hace, cómo funciona y preguntas frecuentes), títulos y descripciones con las palabras que buscan los capitanes, versión en inglés con URL propia (`?lang=en`) enlazada con hreflang en las páginas y en el sitemap, y datos estructurados (JSON-LD) de la aplicación
- Partidos: cada partido es ahora una tarjeta (dos columnas en escritorio, una en móvil) con la fecha completa, el estado en palabras (Victoria, Derrota, Empate, Próximo o Sin resultado), un equipo por fila con sus puntos y el ganador resaltado, el lugar, los convocados de los pendientes y el enlace «Ver partido»
- «Mi jugador» pasa a ser «Mi perfil»: muestra el email y la contraseña con opción de cambiarlos (el email pide la contraseña actual; si entras solo con Google, lo gestiona Google) y el jugador enlazado, que se pulsa para editarlo, o el botón para enlazarte a uno
- Informe PDF de convocatoria: la tabla de convocados cambia «Posición» y «Estim.» por partidos jugados / convocatorias apuntadas (p. ej. 5/8) y la fecha del último partido; sin las tablas de jugadores con más y menos partidos, y letra más grande
- Partidos: buscador por nombre y filtro por rival, listado más compacto y con más contraste; el resultado ya no dice quién gana cada set (solo avisa si un set no es válido); registro de club conectando la cuenta de SNP para traer el equipo y elegir después tu jugador; «Completar equipo» actualiza los puntos de los jugadores que ya estaban, avisa de completar la posición y limita las búsquedas repetidas (salvo el club de pruebas); la cuenta SNP ya no pide el equipo
- Estadísticas nuevas: por número de partido, sets (decisivo, tie-breaks, remontadas, roscos), récords del equipo, ranking SNP de la plantilla, sets clutch y apuntado/alineado por jugador y sets de cada pareja; botón «Alineación sugerida» en las parejas; páginas de uso y salud de los servicios en el back-office
- Seguridad (alertas de code scanning): el flujo de tests pasa a permisos de solo lectura, el estado del proceso en vivo del back-office se escribe como texto, las dependencias (`requirements.txt`, generado desde `requirements.in`) se instalan con versiones y hashes fijados, Bootstrap y Font Awesome se cargan con comprobación de integridad (SRI), la consola SQL limita la longitud de la consulta, el texto de compartir por WhatsApp se monta en la vista sin desactivar el autoescape, la redirección tras guardar una consulta ya no usa la ruta de la petición y portada/«sin club» solo aceptan GET/HEAD

## 06/10/2026

- Amistoso con rival escrito a mano: el formulario ya se envía (los desplegables de equipo ocultos bloqueaban el envío)
- [#95](https://github.com/edubusluc/Zyra/pull/95) Amistosos contra un rival escrito a mano: no se crea ningún equipo, el nombre se guarda en el partido
- Paso entre páginas más fluido: el contenido se desvanece al salir y aparece en cascada al entrar, y las secciones principales se precargan al ir a pulsarlas
- Móvil: los chips de temporada y de tipo de partido y los paneles de resumen de Partidos ya no se salen de la pantalla; paso suave entre páginas con un fundido que no hace perder clics
- Recuperar y cambiar la contraseña con el estilo de la web, la lista de requisitos marcándose al escribir (como en el registro) y el correo de «¿Has olvidado tu contraseña?» con el diseño de los correos de Zyra
- Páginas de privacidad, términos y cookies, contacto en el pie, robots.txt y sitemap, URL canónica y vista previa al compartir, un solo dominio (301 a `SITE_URL`), `/healthz/` para avisar de caídas, fuentes servidas desde la web y mejoras de accesibilidad

## 04/10/2026

- [#88](https://github.com/edubusluc/Zyra/pull/88) Al registrar un club se crea el jugador del capitán enlazado a su cuenta (nombre y apellidos como en SNP; aviso si Google no los da)
- [#87](https://github.com/edubusluc/Zyra/pull/87) Si el capitán es el único miembro, abandonar el club lo elimina con todos sus datos (con aviso y confirmación escribiendo el nombre)
- [#83](https://github.com/edubusluc/Zyra/pull/83) Convocatoria paginada de 20 en 20, botón Resetear por pareja, pareja en el resultado e informe sin guiones
- [#85](https://github.com/edubusluc/Zyra/pull/85) Ajuste de la foto dentro del círculo al subirla, jugadores a la vista en Estadísticas › Jugador y errores en popup
- [#84](https://github.com/edubusluc/Zyra/pull/84) Equipos: gestión solo del grupo y datos copiados del equipo propio; cuenta SNP en tarjeta y errores de «Completar equipo» que llevan a donde se arreglan
- [#86](https://github.com/edubusluc/Zyra/pull/86) Primeros pasos en la portada del club nuevo, registro sin saltar al usuario, un solo club por cuenta y un solo enlace de invitación compartido
- [#82](https://github.com/edubusluc/Zyra/pull/82) Informe PDF de convocatoria en dos páginas también con muchos convocados
- [#81](https://github.com/edubusluc/Zyra/pull/81) Partidos: empates en las estadísticas, selector de temporada con buscador, alineación con buscador y orden SNP al lado, convocatoria más compacta
- [#80](https://github.com/edubusluc/Zyra/pull/80) Enlaces de invitación para varias personas, abandonar el club, elegir jugador con confirmación y foto editable por el capitán

## 03/10/2026

- Textos con «Los Gladiadores» (ruta del README y ejemplo de importación) pasan a Zyra
- [#78](https://github.com/edubusluc/Zyra/pull/78) Revisión completa: fallos arreglados, todo el código documentado y esta web de documentación
- [#77](https://github.com/edubusluc/Zyra/pull/77) Equipos: nuevos con los datos del equipo propio y gestión de varios a la vez
- [#76](https://github.com/edubusluc/Zyra/pull/76) Gráficos de estadísticas, fotos «Validada» y scripts para empezar de cero
- [#75](https://github.com/edubusluc/Zyra/pull/75) Revisión de fotos por el personal, suspensión de cuentas y clubes y emails bloqueados
- [#74](https://github.com/edubusluc/Zyra/pull/74) Revisión de seguridad: página «Sin permiso», permisos y validaciones
- [#73](https://github.com/edubusluc/Zyra/pull/73) Fotos en media/ y validadas con Rekognition; jugadores enlazados a su cuenta
- [#71](https://github.com/edubusluc/Zyra/pull/71) Estadísticas: selector En el equipo / Incluir antiguos en Grado de afinidad
- [#70](https://github.com/edubusluc/Zyra/pull/70) Favicon: líneas interiores de la Z en oscuro
- [#72](https://github.com/edubusluc/Zyra/pull/72) Tests: top de jugadores con el nuevo mínimo de 2 partidos
- [#69](https://github.com/edubusluc/Zyra/pull/69) Estadísticas: selector de temporadas con Todas, las tres últimas y buscador (a main)
- [#67](https://github.com/edubusluc/Zyra/pull/67) Estadísticas: filtro Todos / Competitivos / Amistosos
- [#66](https://github.com/edubusluc/Zyra/pull/66) Partido amistoso y cards de equipo en el formulario de partido
- [#65](https://github.com/edubusluc/Zyra/pull/65) Nombres de jugadores en mayúsculas en toda la web
- [#64](https://github.com/edubusluc/Zyra/pull/64) Balance de partidos por jugador: barras horizontales paginadas

## 02/10/2026

- [#63](https://github.com/edubusluc/Zyra/pull/63) Portada pública centrada y portada del club como antes
- [#62](https://github.com/edubusluc/Zyra/pull/62) Vista móvil revisada, inicio sin scroll y barra que se oculta al bajar
- [#61](https://github.com/edubusluc/Zyra/pull/61) Paginación y buscador por email en invitaciones pendientes
- [#60](https://github.com/edubusluc/Zyra/pull/60) Logo con trazos rectos y esquinas limpias
- [#59](https://github.com/edubusluc/Zyra/pull/59) Registro con Google: un email ya registrado inicia sesión en vez de crear otro club
- [#58](https://github.com/edubusluc/Zyra/pull/58) Nacionalidad del equipo: el scraper SNP abre el país del equipo
- [#57](https://github.com/edubusluc/Zyra/pull/57) PDF de convocatoria: espaciado coherente entre bloques
- [#56](https://github.com/edubusluc/Zyra/pull/56) Miembros: recuperar la invitación por enlace junto a la de email
- [#55](https://github.com/edubusluc/Zyra/pull/55) Mostrar contraseña, requisitos en vivo y capitán que solo invita por email
- [#54](https://github.com/edubusluc/Zyra/pull/54) Partidos: el equipo propio tiene que jugar como local o visitante
- [#53](https://github.com/edubusluc/Zyra/pull/53) Eliminar jugadores sin borrar los partidos en los que jugaron
- [#52](https://github.com/edubusluc/Zyra/pull/52) Formularios: «Elige una opción» en lugar de NONE
- [#51](https://github.com/edubusluc/Zyra/pull/51) Rol de club: Administrador pasa a llamarse Capitán
- [#50](https://github.com/edubusluc/Zyra/pull/50) Equipos: división y nombre único por división
- [#49](https://github.com/edubusluc/Zyra/pull/49) Equipos con categoría y país, avisos de duplicados y tipo de partido

## 01/10/2026

- [#48](https://github.com/edubusluc/Zyra/pull/48) Web en español e inglés con selector de idioma
- [#47](https://github.com/edubusluc/Zyra/pull/47) Calendario propio con el estilo de Zyra al crear partidos
- [#46](https://github.com/edubusluc/Zyra/pull/46) SNP: esperar a que la tabla cargue y lanzar procesos con opciones desde el back-office
- [#45](https://github.com/edubusluc/Zyra/pull/45) Arregla update_snp_scores: "You cannot call this from an async context"
- [#44](https://github.com/edubusluc/Zyra/pull/44) Puntos SNP por lotes con freno anti-bloqueo y reintentos en el envío de informes
- [#43](https://github.com/edubusluc/Zyra/pull/43) PostgreSQL (fase 1): DATABASE_URL, copia de datos desde SQLite y CI con PostgreSQL
- [#42](https://github.com/edubusluc/Zyra/pull/42) Producción segura por defecto, procesos sin duplicados, logs, migraciones en git y CI
- [#41](https://github.com/edubusluc/Zyra/pull/41) Completar equipo: tabla con columnas alineadas
- [#40](https://github.com/edubusluc/Zyra/pull/40) Identificadores públicos con prefijo por objeto en las URLs
- [#39](https://github.com/edubusluc/Zyra/pull/39) SNP: volver a leer la celda del nombre y mostrar la categoría con colores
- [#38](https://github.com/edubusluc/Zyra/pull/38) SNP: arreglar «La tabla de jugadores de SNP está vacía»
- [#37](https://github.com/edubusluc/Zyra/pull/37) SNP: leer solo el nombre del jugador, sin la categoría
- [#36](https://github.com/edubusluc/Zyra/pull/36) Completar equipo desde SNP y apellidos en la edición de jugadores
- [#35](https://github.com/edubusluc/Zyra/pull/35) SNP scraper: wait for each table page to load; log unmatched SNP names
- [#34](https://github.com/edubusluc/Zyra/pull/34) SNP: home notice, cleaner account page, score history chart and new command log
- [#33](https://github.com/edubusluc/Zyra/pull/33) Back-office: fix SynchronousOnlyOperation when running update_snp_scores
- [#32](https://github.com/edubusluc/Zyra/pull/32) SNP scraper: search every iframe for each step
- [#31](https://github.com/edubusluc/Zyra/pull/31) update_snp_scores: live progress, --headed browser and --club by name
- [#30](https://github.com/edubusluc/Zyra/pull/30) Weekly SNP score sync per club (snpgalaxy.com scraper + encrypted captain credentials)

## 30/09/2026

- [#29](https://github.com/edubusluc/Zyra/pull/29) Back-office: autocompletado de campos en la consola SQL
- [#28](https://github.com/edubusluc/Zyra/pull/28) Back-office: traza en directo de procesos y relaciones con punto en la consola SQL
- [#27](https://github.com/edubusluc/Zyra/pull/27) Back-office: consola SQL e importación de datos (fases 4 y 5)
- [#26](https://github.com/edubusluc/Zyra/pull/26) Back-office: procesos programados y log de ejecuciones (fase 3)
- [#25](https://github.com/edubusluc/Zyra/pull/25) Back-office: usuarios conectados y carga de la web (fase 2)
- [#24](https://github.com/edubusluc/Zyra/pull/24) Back-office: dashboard, clubes y usuarios (fases 0 y 1)
