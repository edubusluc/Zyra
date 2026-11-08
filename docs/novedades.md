# Novedades

Registro de lo que entra en `main`, de lo más reciente a lo más antiguo. Cada pull request que
añade o cambia una funcionalidad suma aquí una línea (ver [Mantener la documentación](mantener-documentacion.md)).

## 08/11/2026 · Imagen de «Compartir resultado»

- **Ficha del enfrentamiento · acta cerrada**: «Compartir resultado» envía una imagen vertical (4:5) con el estilo de la web: insignia de la competición, local y visitante con escudo, marcador (lima, rojo o ámbar según el resultado), y una fila por partido con la pareja propia, los sets y los puntos en juego; las parejas no presentadas salen marcadas. En el móvil abre el menú de compartir del sistema con la imagen y el texto; en el ordenador descarga la imagen y abre WhatsApp con el texto.

## 08/11/2026 · Revisión del enlace de disponibilidad

- **Usabilidad**: la tarjeta de la ficha cuenta Sí · No · Pendiente · Sin respuesta (igual que la ventana «Ver respuestas», con botones Sí / No / Pendiente por jugador) y sus tres botones caben en una línea. «Recordar» solo lo envía el capitán, enseña a cuántos escribe, no gasta la espera si no sale ningún correo y dice cuánto falta si hay que esperar. El jugador ve «Respuesta puesta por tu capitán». Un enlace sustituido, un club suspendido o una cuenta de fuera tienen su propio mensaje (y sin datos del partido). La ficha responde sin depender del token. Al volver a cerrar una convocatoria reabierta, el informe solo se reenvía con la casilla «Volver a enviar el informe». El ⓘ usa el mismo componente que las estadísticas.
- **Seguridad**: sesión que se mantiene mientras se use la cuenta (un año desde la última visita; «Mantener la sesión iniciada» en el login, hasta cerrar el navegador si se desmarca, 12 h para el personal) y «Cerrar sesión en los demás dispositivos» en Mi perfil; el servidor comprueba el cierre corto (solo con «pareja no presentada» y ≥2 jugadores), la convocatoria cerrada ya no puede quedarse por debajo del mínimo ni quitar a quien está en una pareja y editar parejas no borra resultados; recordatorios con reserva atómica, tope de 10 al día por club y enlaces con `SITE_URL`; observaciones con aviso de privacidad que se borran al cerrar el acta. El capitán puede bloquear los correos del club a un jugador desde su ficha.

## 08/11/2026 · Convocatoria con menos del mínimo

- **Convocatoria**: se puede crear y editar con menos jugadores que el mínimo de la competición. Al cerrarla por debajo del mínimo la ficha avisa con un popup («se va a cerrar la convocatoria con X jugadores menos») y solo cierra si se confirma, para bajas por lesión u otros motivos.

## 08/11/2026 · Enlace de disponibilidad

- **Inicio · Pendiente**: a los jugadores (y al capitán que también juega) les sale «Responde si puedes jugar: rival, fecha» por cada enfrentamiento de los próximos 14 días en el que su ficha no ha respondido y la convocatoria sigue abierta; lleva a la ficha para contestar y desaparece al responder.
- **Ficha del enfrentamiento**: «¿Puedes jugar?» y, para el capitán, «Disponibilidad» (enlace, WhatsApp y respuestas) van como tarjetas justo debajo de las tarjetas de acción y antes de la «Previa»; en escritorio en dos columnas y en el móvil apiladas. Se quita el resumen de contadores: las cifras están en «Ver respuestas».
- **Texto de WhatsApp**: ahora lista rival, competición, fase (tipo de enfrentamiento y jornada si la hay), fecha con día de la semana, hora y lugar, y pide responder con el enlace; las líneas sin dato se omiten.
- **Ficha del enfrentamiento · Disponibilidad**: el capitán y los gestores comparten un enlace (con texto para WhatsApp) para que la plantilla responda Sí, No o Aún no sé. Hay que iniciar sesión (la sesión se mantiene mientras uses la cuenta) y, si la cuenta no está enlazada a un jugador, se ofrece enlazarla antes de responder. Solo capitán y gestores ven y pueden cambiar las respuestas; los «Sí» llegan marcados al crear la convocatoria. Los jugadores también responden desde la ficha del enfrentamiento («¿Puedes jugar?»). Página del enlace con local VS visitante, hora y lugar destacados y botones Sí / No / Pendiente (Pendiente admite observaciones); tras responder muestra «Has respondido: X» con opción de cambiarla. Recordatorio manual por correo y, con la convocatoria cerrada, el enlace avisa de que ya está cerrada. Una vez respondido, el formulario de la ficha queda plegado («Cambiar respuesta»). Con la convocatoria cerrada las respuestas son solo de lectura; «Reabrir convocatoria» (menú «Más» de la ficha, mientras no haya parejas alineadas) devuelve el enlace y permite cambiarlas. Si la convocatoria se cierra con menos jugadores del mínimo, se alinean las parejas que se puedan formar (de dos en dos) y los partidos restantes quedan como «pareja no presentada» del club (solo SNP, normativa 20.2: una pareja sin presentar reparte los puntos y dos o más pierden 0-12; en la LAPI no existe la pareja no presentada, así que sigue pidiendo el mínimo de convocados), editable después desde las parejas.

## 07/11/2026 · Escudos y nombres alineados en la ficha del móvil

- **Corregido:** en la cabecera de la ficha (vista 3D), escudos, nombres y cintas «Local · división» / «Visitante · división» ya no se desalinean entre sí: cada pieza ocupa la misma fila para los dos equipos, aunque uno tenga logo y otro iniciales, el nombre ocupe 1, 2 o más líneas o la división sea larga. El escudo con foto y el de iniciales miden lo mismo.

## 07/11/2026 · Editar la hora del enfrentamiento

- **Corregido:** el formulario «Cambiar fecha» solo permitía cambiar el día. Ahora es «Cambiar fecha y hora»: se puede modificar o vaciar la hora (HH:MM, opcional) además de la fecha, mientras el acta siga abierta.

## 07/11/2026 · Abrir enfrentamientos jugados en el móvil

- **Corregido:** en la lista de Enfrentamientos, al pulsar un enfrentamiento ya jugado desde el móvil no se abría la ficha (el enlace de la fila estaba oculto). Ahora toda la fila es pulsable, igual que en ordenador, donde ya funcionaba.

## 06/11/2026 · Editar la foto actual del equipo

- **Botón «Editar foto actual»** en los ajustes del equipo y en la edición de jugadores (y en «Mi perfil» del jugador enlazado): reabre el popup de encuadre y zoom sobre la foto ya guardada, sin subir otro archivo. Corregido: el formulario de equipo no montaba el campo de foto con «Subir foto» (el selector nativo seguía a la vista) y ahora sí.

## 06/11/2026 · Escudo 3D más limpio con logos fragmentados

- **El canto del escudo toma los colores del logo** (el mismo logo oscurecido) en lugar de una silueta gris, y es continuo de cara a dorso.
- **El dorso ya no asoma por los huecos** entre las piezas de un logo fragmentado, que antes parecía un bloque; el grosor total baja un poco.
- **Margen alrededor del logo** para que uno recortado al borde de la imagen no se vea como un bloque.

## 05/11/2026 · Ficha del enfrentamiento: interruptor «Vista 3D»

- **Interruptor en la propia ficha** para pasar de la vista con escudos 3D a la vista clásica (la de antes del 3D) y volver. El ajuste se guarda por usuario y es el mismo que ya existía en «Mi perfil».
- **Vista clásica como la de antes**: vuelve el bloque «Previa» de siempre (balance, último y mejor pareja). Las mejoras de funcionamiento siguen en las dos vistas.

## 05/11/2026 · Convocatoria, parejas y resultados: coherencia (fase 4)

- **Una sola marca de «Tu equipo»**: la etiqueta de siempre también al editar un resultado, en lugar de una estrella.
- **Poner resultados**: el borde de cada partido se pone lima si tu equipo gana y rojo si pierde, en cuanto hay ganador.
- **Editar un resultado**: los nombres largos de pareja o equipo ya no se cortan con puntos suspensivos.

## 05/11/2026 · Convocatoria, parejas y resultados: móvil (fase 3)

- **Poner resultados**: en móvil el marcador y los botones Guardar quedan fijos abajo, sin la barra de navegación.
- **Crear y editar parejas**: el orden de juego se pliega en móvil y se despliega con un botón.
- **«Una pareja no se presentó»**: el selector queda tras un enlace y solo aparece si lo necesitas.

## 05/11/2026 · Convocatoria, parejas y resultados: cabecera común (fase 2)

- **Cabecera compacta** en crear y editar convocatoria, crear y editar parejas, poner resultados y editar un resultado: volver a la ficha, los dos escudos con el VS, y el tipo, la competición y la fecha del enfrentamiento. Ya no se pierde el contexto al salir de la ficha.
- **Sin Previa** en crear y editar convocatoria: ya no se repite el balance contra el rival, que está en la ficha.

## 05/11/2026 · Convocatoria, parejas y resultados: arreglos (fase 1)

- **Ganador del partido** en «Poner resultados»: la línea ya muestra solo el nombre del equipo, sin la etiqueta «Tu equipo» ni el nombre de la pareja pegados.
- **Orden de juego**: los puntos SNP salen enteros y con el separador de miles de cada idioma (126 094 pts), igual que en el resto de Zyra.
- **Sin notas visibles**: las reglas del set, la ayuda de la búsqueda de parejas, la explicación de la alineación sugerida, la del orden de juego y la de la lesión pasan a un «i» (al pasar el ratón o pulsar en móvil).
- **Título del partido dentro de la tarjeta**: en «Poner resultados» el «Partido N · pts» y la etiqueta «Guardado» ya no se montan sobre el borde superior de la tarjeta.

## 05/11/2026 · Ficha del enfrentamiento: pulido final (fase 6)

- **Tablet**: los dos escudos quedan a la misma altura aunque un nombre ocupe dos líneas, y el escudo ya no se sale de su columna.
- **Previa en móvil**: los tres últimos marcadores caben en una sola fila.
- **Fechas de la Previa** con el mes localizado (11 ene 2026 / 11 Jan 2026) en lugar de dd/mm/aaaa.
- Revisión de accesibilidad con axe-core en escritorio, tablet y móvil (acta abierta, con parejas y cerrada): sin incidencias. Textos de la ficha revisados en inglés.

## 05/11/2026 · Ficha del enfrentamiento: escudos 3D más ligeros (fase 5)

- **Mismo volumen con menos coste**: el canto de cada escudo pasa de 14 copias completas a 6 capas con solo la silueta y sin filtros, así que la ficha dibuja la mitad de capas 3D y pesa menos en el móvil.
- **El giro se pausa** cuando el escenario sale de la pantalla y en dispositivos táctiles los escudos quedan quietos y ligeramente girados.
- Se elimina la reserva permanente de capa de GPU de los escudos.

## 05/11/2026 · Ficha del enfrentamiento: Previa y acta cerrada (fase 4)

- **Previa en el idioma de la ficha**: victorias, empates y derrotas contra el rival con barra de proporción, forma de los últimos enfrentamientos, partidos a favor y en contra, mejor pareja y los marcadores de los últimos cruces con su resultado (Ganado, Perdido, Empatado). Los puntos de liga solo aparecen en competiciones de liga.
- **Acta cerrada con el mismo escenario**: la convocatoria y los partidos jugados usan las mismas tarjetas con degradado que el resto de la ficha, el partido ganado se resalta en lima y los sets se leen más grandes.

## 05/11/2026 · Ficha del enfrentamiento: tarjeta enfocada (fase 3)

- **Tarjeta enfocada**: la fase que tiene lista (Convocatoria con apuntados o convocados, Parejas con los partidos) ocupa el doble de ancho y de alto en escritorio y lleva la lista dentro; las demás fases se reparten a su lado. En móvil y tablet va primero, a todo el ancho.
- **Sin páginas ocultas**: desaparece el selector «‹ 1/3 ›». La lista se desplaza por dentro, se puede recorrer con el teclado y se abre ya con tu nombre a la vista.
- **Parejas para los jugadores**: quien no gestiona también ve la tarjeta de parejas cuando están alineadas.
- Cerrar convocatoria y cerrar acta siguen siendo formularios con confirmación, ahora en la cabecera de la tarjeta enfocada.

## 05/11/2026 · Ficha del enfrentamiento: escenario «Pista» (fase 2)

- **Pista como escenario**: el fondo es una pista de pádel inclinada con sus líneas y la red como divisor entre local y visitante; el VS (o el marcador) queda sobre la red y los escudos de pie sobre el suelo.
- **Datos en chips**: fecha y hora, y lugar, como chips sobre el escenario; «Local» y «Visitante» como cinta bajo cada nombre (lima el local, acero el visitante).
- **Cuenta atrás**: bajo el VS, «Hoy», «Mañana» o «Faltan N días» mientras el acta está abierta.
- **La lista sale del escenario**: apuntados, convocados o parejas van ahora bajo las tarjetas de acción, así que el escenario mide lo mismo con 3 o con 17 jugadores y los escudos se ven siempre en la primera pantalla del móvil.
- **Tablet**: el escenario usa el diseño de tres columnas desde 768 px.

## 05/11/2026 · Ficha del enfrentamiento: cimientos (fase 1)

- **Escudo de reserva**: un equipo sin foto muestra un escudo con tono propio derivado de su nombre y las siglas de sus dos primeras palabras («AI», «NO»), en vez del escudo lima igual para todos.
- **Fases como lista**: las tarjetas de acción vuelven a ser una lista ordenada con el paso actual marcado; las fases todavía no disponibles (parejas, resultados, acta) salen con candado, sin relieve y con el motivo para lectores de pantalla y como ayuda al pasar el ratón.
- **Aviso personal**: bajo el VS, una pastilla dice si te has apuntado, si estás convocado (con tu partido y tu pareja) o si no lo estás, solo mientras el acta está abierta.
- **Tamaños y fecha**: ningún texto de la ficha baja de 12 px, los controles (paginador, lápiz de fecha, volver) miden 44 px y desaparece el punto suelto entre fecha y lugar en móvil.
- **Por dentro**: todo el CSS de la ficha vive ahora en un solo bloque dentro de las capas del sistema de diseño y usa tokens `--z-stage-*`; se elimina lo que se anulaba (degradado del VS, barra de apuntados oculta, fondo de la tarjeta).

## 05/11/2026 · Inicio con tarjetas del mismo alto

- **Inicio · Próximo enfrentamiento y Pendiente**: en escritorio las dos tarjetas miden siempre lo mismo, la de la más alta. Con un único enfrentamiento (sin selector) la pista ocupa también el hueco que reservaría el selector, y entonces los nombres de los equipos y la ubicación se muestran más grandes. En móvil se apilan con su altura natural.

## 05/11/2026 · TikTok en el pie de página

- **Pie de página**: icono discreto de TikTok junto a los enlaces legales, en todas las pantallas, que abre @zyrapadel en una pestaña nueva. Tiene nombre accesible traducido (es/en).

## 05/11/2026 · Ficha del enfrentamiento: tarjeta de alto fijo y acta cerrada integrada

- **Alto fijo**: la lista no cambia el tamaño de la tarjeta principal tengas más o menos jugadores; las parejas se alinean en dos columnas («Partido N» y la pareja).
- **Acta cerrada**: «Compartir resultado», «Ver estadísticas» (y «Quitar no presentado») van dentro de la tarjeta principal, bajo el VS, y ya no sale «No estás convocado».
- **Tu pareja en lima**: en la ficha nueva ya no hay aviso «Estás convocado»; tu nombre (o tu pareja) sale resaltado en lima en la lista de apuntados, convocados o parejas.

## 05/11/2026 · Ficha del enfrentamiento: lista en filas e iconos planos

- **Lista sin tarjeta**: apuntados, convocados y parejas van en filas, una por nombre, y se paginan de 6 en 6 con un selector «‹ 1/2 ›» (se abre en la página donde está tu nombre).
- **Acabado plano**: sin el destello blanco de los escudos, con el VS en color liso y los iconos de las tarjetas de acción como iconos planos (no emojis); las tarjetas son más grandes.

## 05/11/2026 · Ficha del enfrentamiento: acabado premium

- **Escenario de carbono** con foco de luz que sigue al puntero, borde biselado y franja lima; los escudos reciben luz de borde distinta (local lima, visitante acero), sombra en el suelo y un destello periódico, y se ladean ligeramente con el ratón.
- **VS metálico** con relieve y tarjetas de acción con volumen: se elevan al pasar el ratón, se hunden al pulsar, brillan en el siguiente paso y tienen foco visible y estado desactivado claro.
- **Entrada animada** de escudos, VS, tarjeta y acciones; con «reducir movimiento» no hay animación ni parallax.

## 05/11/2026 · Ficha del enfrentamiento: tarjeta grande y fondo de escenario

- **Tarjeta principal más grande** con los nombres en texto plano separados por puntos; tu nombre va resaltado en lima. Desaparece el aviso «Te has apuntado / Todavía no te has apuntado» mientras la convocatoria está abierta.
- **Informe PDF**: el destinatario solo se muestra en el aviso al cerrar la convocatoria, no en la ficha.
- **Fondo con franja lima**, escudos más grandes, tarjetas de acción con las mismas proporciones y la línea «Sáb 14 nov · 10:00 · Pista».

## 05/11/2026 · Ficha del enfrentamiento: ajustes del escenario

- **Sin título ni listas**: en la vista nueva desaparece el título de la página (queda para lectores de pantalla) y, con el acta abierta, las listas de convocatoria y partidos de debajo: lo cuenta la tarjeta central, que muestra el resto de nombres desplegando «y N más» y marca cada pareja con su resultado.
- **«Local · categoría»** bajo el nombre de cada equipo.
- **Cerrar convocatoria, cerrar acta y «Más»** son tarjetas de acción; el botón «Siguiente» ya no existe en la vista nueva.
- **Cara a cara** siempre visible: sin historial, «Primer enfrentamiento contra…».

## 05/11/2026 · Ficha del enfrentamiento: escenario completo

- **Escenario a todo el ancho**: desaparece el panel lateral. La fecha, el lugar y las etiquetas suben a una línea sobre los escudos y el estado (p. ej. «Convocatoria abierta») queda bajo el VS.
- **Tarjetas de acción**: Convocatoria, Parejas, Resultados y Acta pasan a tarjetas (hecho en lima, siguiente paso en ámbar) que llevan a su pantalla; cerrar convocatoria y acta siguen en el botón «Siguiente».
- **Cara a cara bajo las tarjetas**, como sección propia.

## 05/11/2026 · Ficha del enfrentamiento: interruptor de vista

- **Vuelta a la ficha clásica**: en «Mi perfil» hay un ajuste, activado por defecto, para ver la ficha con escudos en 3D y la tarjeta de apuntados, convocados y parejas. Al desactivarlo cada usuario ve el marcador de siempre, sin escudos ni tarjeta.

## 05/11/2026 · Ficha del enfrentamiento: cara a cara en la previa

- **Previa rediseñada**: victorias, empates y derrotas contra ese rival en cifras grandes, una barra con la proporción y los tres últimos enfrentamientos (fecha, desenlace y marcador, cada uno enlazado), más la mejor pareja contra ellos.

## 05/11/2026 · Ficha del enfrentamiento: previa con escudos 3D

- **Escudos en 3D**: los escudos de los dos equipos se muestran extruidos (sin ficha detrás) y giran despacio y sin parar, en sentidos opuestos; con «reducir animaciones» se quedan quietos. Sin foto, un escudo con las iniciales.
- **Tarjeta sobre el VS**: muestra, según la fase, los apuntados (con barra de progreso), los convocados (con suplentes) y las parejas, y las sustituye una a otra. Con listas largas, enseña los 12 primeros y «y N más».

## 05/11/2026 · Menú «Más» de la ficha en móvil

- **Cabe en pantalla**: el menú de acciones del enfrentamiento (Reenviar, No se presenta…, Cambiar fecha, Eliminar) se alinea con el borde derecho del botón «Más», no supera el ancho de la pantalla y parte el texto en varias líneas en lugar de cortarlo. Lo mismo vale para el menú «⋯» del selector de jugadores.
- **Teclado**: ambos menús se cierran con Escape (el foco vuelve al botón) y al pulsar fuera, y solo hay uno abierto a la vez.
## 05/11/2026 · Hora habitual de juego del equipo

- **Campo nuevo y opcional** en el alta del club y en «Editar equipo» (solo el equipo propio): la hora a la que suele jugar en casa. Los equipos ya creados lo tienen vacío para que el capitán lo complete.
- **Enfrentamiento como local**: el formulario llega con esa hora ya escrita; sigue siendo editable y, si el equipo juega de visitante, se deja en blanco. El día no se propone: se elige siempre.

## 05/11/2026 · Local y visitante centrado

- **Mis estadísticas · Local y visitante**: el gráfico de barras ocupa toda la altura de la tarjeta y queda centrado, con el balance (V – D) alineado debajo, sin hueco vacío cuando la tarjeta se estira a la altura de su vecina, en escritorio y móvil.

## 05/11/2026 · Pendiente fijo y calendario a la vista

- **Inicio · Pendiente**: con varias páginas, la tarjeta mide siempre lo mismo (la de la página más alta) y el selector queda anclado abajo, tenga la página 1, 2 o 3 filas.
- **Enfrentamientos**: el aviso de «hasta el …» se sustituye por una franja «N enfrentamientos más programados» con los meses (p. ej. «Noviembre 3 · Diciembre 5») y el botón «Ver el calendario completo», para que se vea que el calendario está generado.

## 05/11/2026 · Calendario completo sin abrumar

- **Inicio · Pendiente**: solo enseña lo vencido y lo que cae en los próximos 14 días, de 3 en 3 filas, con un selector de páginas de flechas y números que cabe en cualquier ancho (antes las pastillas con fechas se cortaban). Lo más lejano queda a un enlace: «Ver el calendario completo».
- **Inicio de jugadores**: lo que depende de ellos (enlazar la ficha, subir la foto, quién es su pareja) va en la misma tarjeta «Pendiente» que ven capitanes y gestores, junto a la tarjeta del enfrentamiento.
- **Enfrentamientos**: por defecto se ven las actas vencidas, los próximos 14 días y los jugados; el resto del calendario, con «Ver el calendario completo» (`?ver=todo`). Al buscar o filtrar por rival se ven todos.

## 05/11/2026 · Estadísticas: de dónde sale cada porcentaje

- **Base visible bajo cada barra**, en texto pequeño como en «Local y visitante»: «2V – 1D · 3 partidos» en «Por número de partido» y «3 de 4 partidos» o «2 de 3 sets» en las situaciones de set (Equipo, Jugador, Pareja y Mis estadísticas). Ya no depende de pasar el ratón.
- **Ficha del jugador**: «Se apunta» y «Juega cuando se apunta» dicen «N de M convocatorias».
- **Mis estadísticas**: «Local y visitante» suma el balance en casa y fuera de cada competición bajo la gráfica, y «% de victorias por temporada» pone los partidos sobre cada barra.
- **Equipo**: «Asistencia a las convocatorias» indica cuántos apuntados de cuántos posibles y en cuántas convocatorias.

## 05/11/2026 · Estadísticas: plantilla paginada

- **Tabla de plantilla**: en «Estadísticas · Equipo» y en la entrada de «Jugadores» se muestran 15 jugadores por página, con «Anterior» / «Siguiente» debajo. Cambiar de lado (Todos/Local/Visitante) o de orden vuelve a la primera página. Pasar de página, ordenar o cambiar de lado solo actualiza la tabla, sin recargar toda la pantalla. (Issue #256)
## 05/11/2026 · Inicio: partidos semana a semana

- **Carrusel por semana**: «Próximo enfrentamiento» solo enseña los partidos de la semana (lunes a domingo); si esta semana no queda ninguno, enseña la siguiente semana con partidos.
- **«Pendiente» por páginas**: los vencidos se ven siempre arriba y el resto va en páginas de dos semanas, con el mismo selector de pastillas y flechas del carrusel. (PR #251)
## 05/11/2026 · Informes PDF con la fuente actual de la web

- **Títulos y cifras de los PDF** (convocatoria e informe mensual) pasan a Anton, la fuente de títulos de la web, en lugar de Syncopate en cursiva. El logotipo «ZYRA» de la cabecera conserva Syncopate. (Issue #254)

## 03/11/2026 · Inicio: carrusel de próximos enfrentamientos

- **Tarjeta «Próximo enfrentamiento»**: con más de un enfrentamiento abierto, el más cercano va delante y el siguiente (hasta tres en total) queda por debajo, asomando por el lado, más pequeño y difuminado. Sirve sobre todo cuando un fin de semana hay partido de SNP y de LAPI.
- **Cambiar de tarjeta**: selector debajo con una pastilla por enfrentamiento (competición y día) y flechas en escritorio; también arrastrando (la tarjeta sigue al dedo), tocando la que asoma o con las flechas del teclado. El movimiento es más suave y no hay saltos. Con un solo enfrentamiento todo queda como antes. (PR #246)

## 03/11/2026 · Ficha del jugador sin «Equipo: X %»

- **Más espacio en la cabecera**: se quita la comparación «Equipo: X %» junto al anillo de victorias (confundía con pocos partidos y no decía con qué se comparaba); el anillo y el balance ocupan ese hueco.
## 03/11/2026 · Plantilla: subida o bajada de puntos SNP

- **Evolución en puntos**: la columna «Evolución» de la tabla de plantilla muestra cuántos puntos SNP ha subido o bajado cada jugador (▲ +N / ▼ -N) en lugar de la mini línea. Si la última actualización no cambió ningún valor del equipo, se mantiene la subida o bajada de la última en la que sí hubo cambios, en vez de poner «=» a todos.

## 03/11/2026 · Estadísticas: equipo sin enfrentamientos cerrados

- **Sin callejón**: si el equipo activo no tiene enfrentamientos cerrados y otro equipo de la cuenta sí, la tarjeta vacía lleva el selector de competición, dice qué equipo está vacío y ofrece un botón para ver el otro. Nunca cambia de equipo por sí sola.
## 03/11/2026 · Aviso de nuevo gestor según competición

- La tarjeta «Ahora eres gestor del equipo» ya no menciona la cuenta SNP ni «equipos» en los clubes LAPI: allí dice que el capitán sigue gestionando los miembros y las invitaciones.

## 02/11/2026 · Back-office: clubes por competición

- **Dashboard**: una tarjeta de «Clubes SNP» y otra de «Clubes LAPI» con el total, los activos y las altas de 30 días. Cada club es un espacio de una sola competición y tiene un único equipo propio, así que cada uno cuenta una vez y las dos tarjetas suman el total de «Clubes».
- **Lista de clubes**: columna «Competición» y filtro por competición, que también enlazan las tarjetas.

## 02/11/2026 · Estadísticas: fase 9 (Enfrentamientos)

- **Lista para gestionar**: desaparece el resumen de cinco cifras (Jugados, Ganados, Empatados, Perdidos, Pendientes) y no lo sustituye ningún indicador: los pendientes ya están en «Requieren acción» y el balance, en Estadísticas › Equipo. Los títulos «Próximos» y «Jugados» ocupan todo el ancho también en la vista de jugador.
- **Cerrados en una línea**: fecha, rival, competición, tipo o jornada y el resultado leído desde nuestro equipo («1–2» y D/V/E), igual para capitán y jugador. El recorrido de cuatro pasos queda solo en los pendientes del capitán o gestor; los jugadores siguen viendo la tarjeta de «Próximos».
- **Un solo estado en el acta**: desaparecen la insignia de la cabecera y la etiqueta «Acta cerrada»; con el acta cerrada tampoco se muestran las cuatro fases. El estado está junto al marcador.
- **«Previa» solo antes de jugar**: con el acta cerrada, en su lugar, el enlace «Historial contra [rival]» a su ficha en Estadísticas › Rivales (todas las temporadas).

## 02/11/2026 · Estadísticas: fase 8 (densidad, móvil y accesibilidad)

- **Sin notas descriptivas**: desaparecen los textos de una línea bajo los títulos de las tarjetas; lo que hace falta explicar (mínimos, reglas de puntos, cómo se alinean las parejas) va en un tooltip «i» junto al título, que se abre al pasar el ratón o al pulsar en móvil.
- **Secciones por nivel**: cada sección declara su nivel (`data-level`: comprender, comparar o profundizar). En móvil solo las de «comprender» están siempre abiertas; el resto se pliega, con un resumen en la cabecera (p. ej. «23 jugadores»). Equipo en móvil llega plegado y sin desbordar horizontalmente, y el globo del tooltip ya no ensancha la página.
- **Mismas palabras en todas partes**: enfrentamiento (jornada o cruce entre dos equipos) frente a partido (parejas dentro de él); «Partidos jugados» con su unidad al lado de la cifra, y «Convocatorias» con «a las que se apuntó» para distinguir apuntarse de ser convocado.
- **Gráficos accesibles**: todos los lienzos van ocultos a los lectores de pantalla y el contenedor lleva en su etiqueta el título y los valores de cada serie (también en Parejas).
- **Limpieza**: se eliminan cinco plantillas que ya no usaba ninguna vista.

## 02/11/2026 · Estadísticas: fase 7 (Parejas y Rivales)

- **Parejas · todas las parejas**: sin pareja elegida, la entrada es la lista de todas las que han jugado juntas (partidos, V-D y %), con buscador por nombre y orden por más partidos, mejor %, peor % o nombre. Desaparecen «Mejores parejas» y «Parejas por mejorar» (con umbrales distintos); no hay selector de mínimo, la base va en cada fila.
- **Ficha de pareja que escala con la muestra**: con un solo partido juntos solo se ven el resumen y el partido; la racha, la forma, Local y visitante, los sets y el rendimiento por temporada aparecen a partir de 2. El gráfico «Partidos jugados» solo con dos temporadas o más y la evolución del % con las mismas reglas que en Jugador (temporadas de 5 partidos o más); el «Cambio» solo entre temporadas con muestra.
- **Pareja en LAPI**: el encabezado dice «N partidos juntos» (ya no «Pareja sorteada N veces»), la tabla por temporada no tiene la columna Puntos y la columna Tipo de «Últimos partidos juntos» se rellena con el tipo y la jornada («Liga · J5»).
- **Rivales con %**: cada rival lleva su % de victorias; se ordena por mejor % o «Peor primero» (el rival contra el que peor nos va) en lugar de por balance. Las cabeceras de puntos son explícitas: «Puntos de liga» en LAPI y «Puntos a favor-en contra» en SNP.
- **Ficha de rival**: el resumen son una línea (enfrentamientos, G-E-P con %, puntos y último resultado); «Racha contra ellos» pasa a «Últimos enfrentamientos» y «Mejores parejas contra ellos» a «Parejas contra ellos», con las mejores y las peores (mínimo de partidos).
- **Sin tarjetas vacías**: la evolución de puntos SNP del jugador, el compañero, Local y visitante y las convocatorias de «Yo» no se dibujan cuando no hay datos.

## 02/11/2026 · Estadísticas: fase 6 (comparar)

- **Sets iguales en todas partes**: Equipo, Jugador, Pareja, «Yo» y el informe mensual en PDF usan las mismas situaciones y nombres: Tras ganar el 1.er set, Tras perder el 1.er set, Tie-breaks, Set decisivo y Roscos a favor. Se dibujan con el estilo de barras del antiguo «Sets clutch» (título con su descripción, barra y %; los casos, en el tooltip) y las que no tienen ninguno no se muestran; en «Yo» cada situación lleva una barra por competición. «Sets ajustados» y «Super tie-break» salen de la web (el PDF conserva el super tie-break).
- **Local y visitante**: Jugador y Pareja comparten un bloque con la unidad escrita (porcentaje, V-D y partidos). Equipo conserva sus dos tarjetas «Ganados como local / visitante», ahora con el texto «enfrentamientos ganados / total».
- **Yo · gráficos**: «Ganados por temporada» (volumen) pasa a «% de victorias por temporada» por competición, con los partidos de cada barra en el tooltip. Las convocatorias a las que te apuntas se muestran como cifra por competición; la línea solo aparece con dos temporadas o más.
- **Compañeros**: «Grado de afinidad» se sustituye por la lista de Compañeros, con partidos, V-D y % real, la pareja habitual primera (como en la cabecera), el mejor y el peor % entre quienes tienen 5 partidos o más, y enlace a la pareja. La afinidad suavizada solo desempata.
- **Evolución sin falsas tendencias**: el gráfico «% de victorias por temporada» de la ficha del jugador solo usa temporadas con 5 partidos o más (y al menos dos), con los partidos bajo cada punto, y el «Cambio» de la tabla solo se calcula entre temporadas con muestra. «Partidos jugados» pasa a «Profundizar».
- **Detalle por temporada**: la tabla baja de 9 a 5 columnas (Temporada, Jugados, V-D, %, Cambio) y los puntos, las convocatorias y el alineado están en «Profundizar».

## 02/11/2026 · Estadísticas: fase 5 (tabla de plantilla)

- **Tabla de plantilla**: sustituye a los dos Top 5 y a las tarjetas «Más victorias» y «Más partidos jugados» de Equipo. Una fila por jugador con Jugados, V-D, % de victorias, «Se apunta» (% de convocatorias cerradas a las que se apuntó) y, en SNP, los puntos con su último cambio. Se ordena pulsando la columna y tiene el conmutador Todos · Local · Visitante.
- **Sin mínimo de partidos**: cuenta el % de todo el que ha jugado; quien no ha jugado ninguno va apagado al final, y así se ve también a quien rinde peor.
- **«Se apunta» sigue el filtro**: con Local o Visitante cuenta solo las convocatorias de los enfrentamientos en los que el equipo juega en ese lado.
- **Evolución SNP en la tabla**: cada jugador lleva una mini línea con sus últimas actualizaciones y los puestos que sube o baja en el ranking desde la anterior, para ver el «pique» semanal sin un gráfico aparte.
- **Jugadores**: sin jugador elegido, la entrada es esta misma tabla (con filtro de temporada y tipo) y cada fila abre su ficha; desaparecen la cuadrícula de avatares y el texto de ayuda.
- **Puntos SNP**: desaparece el bloque aparte (y su gráfico de la media del equipo). Los puntos, el cambio y la evolución de cada jugador están en la tabla; la media del equipo y la fecha de la última actualización (con aviso a los 6 días) van en una línea sobre la tabla.
- **Récords**: cinco (racha de victorias con «sin perder» en un «i», mayor victoria, peor derrota, mejor temporada y pareja con más victorias).
- **Profundizar**: la asistencia a las convocatorias y el balance por jugador (partidos de 3 y 2 puntos) pasan a dos secciones plegadas; no se pierden.

## 02/11/2026 · Estadísticas: fase 4 (comprender)

- **Equipo · balance**: una sola lectura (victorias, empates y derrotas, el % con su base «de 14 enfrentamientos» y una barra segmentada si hay empates). Desaparece el pie «Ganados · 7 de 14».
- **Equipo · forma y racha**: los últimos 5 enfrentamientos con los mismos círculos que Jugador, Pareja y Rival, y la racha actual.
- **Equipo · media SNP**: se quita la tarjeta «Media por jugador», que repetía la «Media del equipo» del ranking SNP; el ranking indica «Actualizado el dd/mm/aaaa» y avisa si hace más de 6 días.
- **Equipo · Liga (LAPI)**: un solo bloque con los puntos de la última jornada, las jornadas jugadas y los elegibles para las fases finales; quienes no lo son salen en un desplegable con las jornadas que les faltan. La cita del reglamento pasa a un «i». «No presentados y lesiones» solo aparece si hay alguno.
- **Yo (Mis estadísticas)**: el % de victorias, global y por competición, con el número de partidos jugados; «te apuntaste a X de Y» pasa a una cifra propia.
- **Yo · Sets**: la tarjeta muestra las mismas cuatro situaciones que el «Sets clutch» de la ficha (Tie-breaks, Cerrar el partido, Remontadas y Roscos a favor) con su descripción a la vista, no en un «i».
- **Ficha del jugador**: junto a su % de victorias aparece «Equipo: X %» (los partidos de todo el club en el mismo periodo), y los puntos SNP indican cuándo se actualizaron, con aviso a los 6 días.

## 02/11/2026 · Estadísticas: fase 3 (navegación y fichas)

- **Pestañas**: cinco (Yo, Equipo, Jugadores, Parejas, Rivales), que caben en 390 px sin deslizar. «Yo» sustituye a «Mis estadísticas» y a «Jugador · Yo» y aparece en cuanto tienes jugador enlazado; con un solo equipo abre directamente tu ficha.
- **Ficha del jugador en móvil**: foto y rol en una fila, nombre a ancho completo, datos en una línea, botones lado a lado y el anillo con su texto «de victorias».
- **Ficha del jugador**: «Editar jugador» y las advertencias son botones visibles bajo el nombre (antes eran enlaces de texto pequeños).
- **Ficha única de jugador**: Plantilla y Estadísticas enlazan a la misma ficha (foto, posición, mano, desde, puntos SNP, «Editar» y, para capitán y gestores, el número de advertencias). Desaparece la pestaña «Resumen» y la ficha duplicada de Plantilla; la antigua URL redirige.
- **Advertencias**: salen de Estadísticas y se abren desde Plantilla (solo capitán y gestores).
- **Equipos rivales**: el catálogo de Enfrentamientos y de Equipo se llama «Equipos rivales», para no confundirlo con la pestaña Rivales de Estadísticas.
- **Local y visitante (jugador y pareja)**: la barra solo pinta el tramo de ganados o de perdidos que tiene partidos; antes un 0 dibujaba un círculo suelto.
- **Tipo**: en Equipo y Jugador el desplegable «Tipo» muestra «Competitivos» cuando es el filtro por defecto (antes salía en blanco).

## 02/11/2026 · Estadísticas: fase 2 (contexto único)

- **Competición**: Equipo sigue al equipo activo como el resto de pantallas (Jugador, Parejas, Rivales). Si eliges LAPI en una pestaña, todas abren LAPI; se elimina la clave de sesión propia de Equipo.
- **Tipo de enfrentamiento**: Estadísticas cuenta por defecto solo los competitivos (los amistosos no se mezclan, igual que «Mi forma» en Inicio). «Todos» sigue disponible en el filtro Tipo, y el balance de Inicio coincide con el de Jugador · Yo con los filtros por defecto.
- **Rivales**: la lista y la ficha usan la temporada y el tipo por defecto del resto (antes sumaban todas las temporadas y los amistosos) y la lista incorpora el filtro de tipo.
- **Filtros**: Competición · Temporada · Tipo van en la misma fila, justo bajo las pestañas, en todas las pantallas de Estadísticas.
- **Selector de competición**: el desplegable cerrado muestra también SNP o LAPI junto al nombre del equipo, para distinguirlos cuando se llaman igual.

## 02/11/2026 · Estadísticas: fase 1 (datos que no inducen a error)

- **Mis estadísticas**: «Local y visitante» pasa a mostrar el % de victorias en casa frente a fuera de cada competición (antes repetía ganados y perdidos, que ya dicen las filas de arriba). Sus barras y las de «Ganados por temporada» son más anchas, con la cifra dentro y sin huecos grandes, como en «Puntos de liga». «Ganados por temporada» solo aparece con «Todas»; con una temporada elegida no tiene sentido y se oculta.
- **Equipo**: se quitan «Juegos como local» y «Juegos como visitante» (juegos de tenis sumados, que repetían «Ganados como local/visitante» con otra unidad).
- **Equipo · Plantilla y fases finales (LAPI)**: indica su temporada y calcula siempre la temporada en curso; con una temporada pasada elegida no se muestra.
- **Equipo · SNP**: «Puntos de liga» pasa a llamarse «Puntos por enfrentamiento», porque SNP no tiene liga (LAPI mantiene «Puntos de liga»).
- **Móvil**: el % de victorias del jugador y de la pareja se ve también en el móvil (anillo bajo el nombre).
- **Racha actual**: la cifra va en lima si es de victorias y en rojo si es de derrotas.

## 02/11/2026 · Fila única de filtros

- **Un solo bloque de filtros**: Competición, Temporada y Tipo son desplegables en una sola fila, igual en Enfrentamientos, Calendario, Plantilla, Club, Miembros y todas las pestañas de Estadísticas (Mis estadísticas, Equipo, Jugador, Parejas, Rivales y Advertencias). Cada uno dice su valor y se marca en lima si no es «Todas».
- Dentro de Competitivos, el tipo concreto se elige en un cuarto desplegable «Competitivo» de la misma fila. Se quitan las píldoras de competición y los chips de tipo.

## 02/11/2026 · Estadísticas rediseñadas (fases 5, 6 y 7: Parejas, Rivales y Advertencias)

- **Parejas**: cabecera lima con la pareja, su balance y el % de victorias («Pareja habitual del partido N» en SNP, «Pareja sorteada N veces» en LAPI), racha, forma reciente, victorias como local y visitante con barras, sets, mejores parejas y «Últimos partidos juntos» (en LAPI con tipo y jornada en vez de número de partido y sin columna de puntos). Con una pareja elegida ya no se repite «Mejores parejas». Con «Todas», «Detalle por temporada» resume cada temporada; con una temporada concreta no sale la evolución del % y el detalle lista los partidos de la pareja en ella. Los gráficos siguen el estilo de Zyra.
- **Rivales**: la lista muestra «Pts liga» en LAPI; la ficha del rival estrena cifras (la primera en lima), «Racha contra ellos» y, en LAPI, los puntos de liga de cada cruce. Un rival que no se presentó aparece con la etiqueta «No presentado».
- **Advertencias**: tres cifras con la de advertencias en ámbar, «Por jugador» y el nuevo gráfico «Por motivo», con el recuento de cada tipo.

## 02/11/2026 · Ficha del jugador: evolución por temporadas

- Con **«Todas»** vuelven «Partidos jugados» (ganados y perdidos por temporada), «Evolución del % de victorias» y la tabla «Detalle por temporada», con el estilo de gráficos de Zyra. Con **una temporada concreta** se ve solo la tabla de «Partidos jugados» de esa temporada.

## 02/11/2026 · Equipo: ajustes de la fase 3

- **Puntos de liga**: con una temporada elegida, una barra por jornada (o enfrentamiento en SNP); con «Todas», una barra por temporada.
- **Balance de partidos por jugador**: barras finas y redondeadas, separadas y sin ejes. Vuelve la tabla de **Ranking SNP** (sección «Puntos SNP») y los gráficos de **Juegos como local** y **como visitante** en Gráficos.
- Las cifras del inicio pasan a «Ganados como local» y «Ganados como visitante» (partidos ganados / total). Nuevo **menú lateral** «En esta página» en escritorio que marca la sección visible.

## 01/11/2026 · Estadísticas rediseñadas (fase 3: Equipo · SNP y LAPI)

- **Equipo** como en el diseño aprobado: tarjeta lima de «Balance de enfrentamientos» (con empates solo si la competición los admite y, en SNP, las eliminatorias 6-6 a favor y en contra), cifras de juegos en casa y fuera y media de puntos SNP por jugador (SNP).
- **Puntos de liga**: barras pegadas con los puntos de cada jornada (LAPI: 4, 3, 1 o 0) o de cada enfrentamiento (SNP, de 12 posibles), solo las últimas 7; en LAPI, «Plantilla y fases finales» con elegibles según el reglamento 8.2. «Eliminatorias 6-6» pasa al balance.
- **Top 5**: mejores jugadores como local y como visitante. **Partidos y sets**: «Por número de partido» (SNP), «Sets» con Tie-breaks, Cerrar el partido, Remontadas y Roscos a favor, cada uno con su texto, y en LAPI «No presentados y lesiones». **Récords** con las ocho tarjetas, **Balance de partidos por jugador** (SNP).
- Los títulos de sección vuelven a verse en escritorio (el botón de plegar los ocultaba), los chips de tipo son los de la competición (en LAPI: Liga, Playoffs, Fase final) y desaparece el aviso «Cada competición puntúa distinto» de las pantallas de estadísticas. Se quitan de Equipo los gráficos de juegos como local y visitante (están en la tarjeta del balance), ganados por año y la tabla de ranking SNP; la asistencia por temporada sigue en Gráficos.

## 01/11/2026 · Estadísticas rediseñadas (fase 2: ficha del jugador · SNP y LAPI)

- **Jugador** (y «Mi ficha»): tarjeta lima con nombre, rol, pareja habitual, puntos SNP y puesto del equipo (o jornadas de liga en LAPI), anillo de % de victorias y balance; cifras de Jugados, Racha, Puntos ganados (de los posibles) y Convocados (en LAPI, Jornadas y «1 punto cada uno»).
- Forma reciente, Local y visitante con barras fijas, «Partidos y sets» (SNP: por número de partido; LAPI: sets y fases finales con la regla de elegibilidad), Asistencia y afinidad, y puntos SNP o partidos por temporada. Al final queda el listado de «Partidos jugados» (de la temporada elegida o de todas); se elimina la tabla de detalle por temporada.
- «Sets clutch» lista Set decisivo, Tie-breaks, Remontadas, Cerrar el partido y Sets ajustados, cada uno con un texto descriptivo bajo el nombre. En LAPI no hay gráfico por temporada y el de puntos SNP solo sale con «Todas».
- Los filtros de tipo pasan a chips por tipo de enfrentamiento, y los «i» explican cada medida (también al pulsar en móvil).

## 01/11/2026 · Pulido visual, textos y back-office (auditoría UX/UI, fase 6)

- **Resultados**: el equipo propio lleva la etiqueta «Tu equipo» en lugar de una estrella, que se leía como «ganador».
- **Alinear parejas** (escritorio): la barra de guardar va en la columna lateral, bajo «Orden de juego», y ya no tapa la última pareja.
- **Rivales**: se quita la tarjeta lima «Nuevo rival» del final de la lista; queda el botón de la cabecera.
- **Equipo**: los accesos rápidos son botones iguales de 44 px en una rejilla a todo el ancho.
- **Navegación**: la barra inferior del móvil ya no se esconde al bajar (solo la cabecera), y el cambio de página usa un fundido de 0,2 s sin retardos.
- **Portada**: las líneas de la pista se desvanecen bajo el texto del titular.
- **Iniciar sesión**: el campo de usuario sugiere «ana@correo.com», la contraseña no repite su etiqueta y la cabecera ofrece «Registrarme».
- **Formularios**: las etiquetas ya no llevan dos puntos y los títulos «Editar jugador» y «Editar equipo» van en minúscula. Un nombre o unos apellidos de jugador necesitan al menos una letra («GON ,» ya no se admite).
- **Mi perfil**: en escritorio, en dos columnas (Cuenta y Mis fichas | Preferencias y Eliminar mi cuenta).
- **Back-office**: ninguna tabla amplía la página en móvil (el texto oculto de las tablas con scroll propio la desbordaba) y el árbol de tablas de la consola SQL usa `<details>` sin botones dentro del resumen, con objetivos de al menos 24 px y los dos menús laterales con nombre propio.
- **Enfrentamientos**: «Requieren acción» es solo para quien gestiona ese equipo; los jugadores ven únicamente «Próximos» y «Jugados».
- **Sin cambios**: «Enfrentamientos» cabe en la barra inferior a 390 px con la letra a 12 px (se hizo en la fase 4), así que no hace falta el nombre corto «Partidos».

## 01/11/2026 · Estadísticas rediseñadas (fase 1: Mis estadísticas · Todas)

- **Cabecera de Estadísticas** como en el diseño aprobado: pestañas en mayúsculas sin iconos, fila «Competición» (Todas · SNP · LAPI con su color) con el contexto a la derecha, temporada y chips de tipo (Todos · Competitivos · Amistosos).
- **Mis estadísticas · Todas**: tarjetas de Jugados (lima), Ganados y Perdidos; una fila por competición con borde de su color y «N jugados · XV YD · te apuntaste a a de b» y gráficos en dos columnas: Sets (dos barras finas por situación, con un «i» que explica cada una), Local y visitante (ganados y perdidos por competición), Ganados por temporada (apilados con el total) y Convocatorias (líneas sin ejes con el último valor).

## 01/11/2026 · Flujos y densidad (auditoría UX/UI, fase 5)

- **Estadísticas en móvil**: los filtros se recogen en una sola fila «Filtros · …» y cada sección se pliega bajo su título (solo la primera queda abierta; los enlaces del índice abren la suya). La página de equipo pasa de unos 7.700 px a unos 3.200. Los bloques con pocos datos muestran un único aviso compacto («Se mostrará cuando…») en lugar de un gráfico casi vacío, y el de afinidad ajusta su altura a las barras.
- **Rivales en móvil**: cada rival es una tarjeta con nombre, último resultado y balance.
- **Ficha del enfrentamiento**: el estado «Acta cerrada» ya no se repite en el aviso final (que queda solo con las acciones) y la barra «Siguiente» es de una línea en móvil, con la ayuda solo si bloquea el paso.
- **Convocatoria**: una sola línea de datos por jugador (posición · puntos · jugó), buscador y filtros fijos al recorrer la lista y las acciones masivas en un menú «⋯».
- **Resultados en escritorio**: panel lateral fijo con el marcador global en vivo y las acciones de guardado.
- **Miembros**: invitar va arriba, las reglas de los roles en un plegable «¿Qué puede hacer cada rol?» y el título ya no repite la competición. **Registro de equipo**: la explicación del capitán va en un plegable.
- **Inicio**: «Pendiente» muestra solo el rival y la acción en la línea de la fecha; los jugadores ven «Tus pendientes» (enlazar la ficha, subir la foto, quién es su pareja).
- **Portada**: ejemplo del «Próximo enfrentamiento» con datos de muestra y funciones en carrusel en móvil. La elección de equipo al crear (rival, jugador, enfrentamiento) usa tarjetas grandes lado a lado.
- **Ajustes tras revisar la fase 5**: en una temporada sin partidos, «Por número de partido» y «Sets clutch» ocupan toda la tarjeta con solo el aviso «No hay datos para mostrar» (con partidos, «—» en los números sin jugar). Crear rival añade, en escritorio, la tarjeta «Así se verá» (como al crear un enfrentamiento), que se rellena sola con el nombre, la división, la localización, la categoría y el país. En el registro, el botón de Google ya no se solapa con el formulario. La «Previa» enlaza con el último enfrentamiento contra ese rival. Las tarjetas del selector de convocatoria miden lo mismo. «¿Qué puede hacer cada rol?» pasa a una lista con la insignia de cada rol. En escritorio, el registro de equipo pone la presentación a la izquierda y el formulario a la derecha, para ver los campos sin hacer scroll. «Tus pendientes» se separa de la tarjeta de enfrentamientos, la tilde de «Sáb» de la portada ya no choca con el texto de arriba y crear un enfrentamiento ya no repite el equipo donde se creará.

## 01/11/2026 · Sistema de diseño (auditoría UX/UI, fase 4)

- **Capas CSS**: `style.css` declara `@layer overrides, base, vendor, tokens, components, screens` e importa Bootstrap y Font Awesome en su capa. Las reglas propias ganan a Bootstrap sin subir especificidad; los `!important` que pisan utilidades de Bootstrap viven en la capa `overrides`. Se comprobó con capturas antes y después (sin diferencias visibles).
- **Escalas con tokens**: ocho tamaños de letra (`--z-fs-xs` … `--z-fs-3xl`, mínimo 12 px) y cuatro radios (`--z-radius-xs/sm/-/lg`) sustituyen a unos 40 y 25 valores sueltos.
- **Títulos de sección** con una sola voz (Anton, sin el override tardío), **insignia de división** neutra (el color queda para estados) y **mayúsculas** solo en títulos, kickers y nombres: botones, etiquetas, cabeceras de tabla e insignias van en caja de oración.
- **Fechas** en el mismo formato en toda la web (`date_short`, `date_long`, `date_day`, `date_day_time` en `zyra_format`) y **sets** sin ceros inútiles.
- **Iniciales** cuando un jugador no tiene foto (`includes/player_avatar.html`), con aro neutro.
- **Nombres de jugador** en caja de título («Alberto Montaño»; `proper_name` en `players/models.py`): `full_name` y `short_name` ya no devuelven mayúsculas, que quedan solo en titulares (CSS) y en el PDF de convocatoria. Sustituye a la decisión de la PR #65.
- **Textos**: «Plantilla» para los jugadores del equipo, «Crear rival», «Nuevo jugador» y «equipo» en lugar de «club» en los avisos.

## 01/11/2026 · Espacios (auditoría UX/UI, fase 3)

- **Altas sin equipo por defecto**: quien gestiona equipos de SNP y de LAPI elige en cuál crea un rival o un jugador (pantalla «¿En qué equipo…?»), y los formularios dicen «Se creará en SNP · …». En Miembros, el selector de arriba y «Invitas a …» dejan claro a qué equipo se invita.
- **Selector de competición único**: en Estadísticas, Enfrentamientos, Calendario, Jugadores, Rivales, Club y Miembros es el mismo control segmentado, con la insignia SNP/LAPI y el nombre del equipo.
- **Enfrentamientos agrupados**: el listado va en «Requieren acción» (acta abierta con la fecha pasada), «Próximos» (el más cercano primero) y «Jugados».

## 01/11/2026 · Móvil primero (auditoría UX/UI, fase 2)

- **Estadísticas**: las pestañas se deslizan en horizontal dentro de su fila (ya no ensanchan la página a 375 px) y «Mis estadísticas» pasa a «Mías» en móvil.
- **Formularios**: los campos miden 16 px como mínimo, así Safari en iPhone ya no amplía la página al enfocarlos.
- **Pantallas táctiles**: botones, chips e iconos llegan a 44 px de alto.
- **Inicio en móvil**: primero los equipos, luego el próximo enfrentamiento y «Pendiente», y después los avisos y «Primeros pasos» (que se pliega a lo esencial). El panel del próximo enfrentamiento queda centrado y, en móvil y tableta, también dibuja la pista de pádel de fondo (de pie en móvil, tumbada en tableta).
- **Ficha del enfrentamiento**: los convocados se muestran como nombre y primer apellido, en hasta dos líneas y sin la pastilla «Convocado». El jugador ve solo las fases de convocatoria y acta, y si se había apuntado le dice que avise a su capitán si cambia su disponibilidad.
- **Fecha pasada**: la lista y el Inicio usan el mismo estado rojo «Vencido · …».
- **Enfrentamientos, Jugadores y Rivales**: en móvil, la acción principal va primero y lo secundario se recoge en un menú «Más».
- **Balance por jugador**: cada tramo de barra lleva su cifra, las series perdidas llevan rayas además del rojo y hay una tabla equivalente para lectores de pantalla.

## 01/11/2026 · Accesibilidad y lectura del resultado (auditoría UX/UI, fase 1)

- **Marcador de la ficha**: los nombres de los equipos ya no se parten a mitad de palabra; el tamaño se ajusta al ancho del marcador y en móvil y tableta los dos equipos van debajo del resultado.
- **Lima solo para lo tuyo**: el resultado se pinta en lima si gana tu equipo, en rojo si pierde y en blanco si empata; en los partidos y en «Meter resultados» el lima solo marca los sets de tu equipo, y cuando gana el rival se indica en neutro.
- **Campos de formulario**: bordes con contraste suficiente (3:1, WCAG 1.4.11) en campos, desplegables, calendario y casillas.
- **Error del servidor**: nueva página 500 propia, con el estilo de Zyra y un botón para volver al inicio.
- **Enlaces dentro de texto** siempre subrayados (no solo por color), un título principal oculto para lectores de pantalla en el Inicio del club y encabezados sin saltos en las estadísticas de jugador.

## 01/11/2026 · Más aire en Inicio y Enfrentamientos

- **Gráficos de estadísticas**: estilo común en todas las vistas (`static/js/chart-style.js`): sin cuadrículas ni ejes, barras muy redondeadas con su cifra dentro, líneas lima con área suave, tooltips oscuros y barras de progreso más gruesas.
- **Mis estadísticas, Advertencias y «Crear rival»** siguen el mockup: datos grandes en Anton, una tarjeta por competición con franja de color, advertencias como tarjetas con fecha, jugador, motivo y enfrentamiento, y formulario de rival con campos holgados y botón a todo el ancho.
- **Estadísticas**: el primer dato de «Mis estadísticas» y la ficha de jugador va en lima, «Mejores parejas» es un panel lima y el recuento de advertencias se marca en ámbar.
- **Rivales**: tarjetas con escudo, nombre grande y etiquetas separadas por una línea, tarjeta lima «Nuevo rival» al final y formulario de creación con cabecera y ancho propios.
- **Portada pública**: nuevo diseño con bloque lima sobre la pista, «Convoca. Alinea. Gana.», tarjetas de las competiciones disponibles (SNP y LAPI), funciones, pasos numerados, guías y preguntas.
- **Inicio y listado**: los botones de los avisos («Nombrar gestor», «Registrar cuenta») arrancan en el mismo borde y las tarjetas de enfrentamiento y las filas de «Pendiente» tienen más separación para reducir el ruido visual. En el bloque «Próximo enfrentamiento» el contenido sube, los nombres de los equipos son más grandes y el botón «Ver convocatoria» más pequeño.

## 31/10/2026 · Nuevo estilo visual (fase 3: estadísticas)

- **Estadísticas del equipo**: el balance de enfrentamientos pasa a bloque lima con cifras gigantes (victorias, empates, derrotas), barra y datos en fichas oscuras. Títulos de sección y tarjetas en Anton, y los Top 5 llevan barra de porcentaje por fila.
- **Crear enfrentamiento**: en escritorio, a la derecha del formulario aparece «Así se verá», una tarjeta lima que se rellena en vivo con el tipo, la fecha, la hora, el lugar y los equipos (`static/js/match-form.js`).

## 30/10/2026 · Nuevo estilo visual (fase 2: listado de enfrentamientos)

- **Ficha del enfrentamiento**: marcador y nombres de los equipos en grande (en escritorio, sobre la pista 2:1 con la red entre local y visitante), banner del tipo («Liga · Jornada 2»), desenlace y lugar al lado, cuatro tarjetas de estado con cifra y barra (convocatoria, parejas, resultados, acta) y lista de convocados identificable: avatar, nombre en mayúsculas, pareja P1/P2/P3 con su compañero y etiqueta Convocado o Suplente.
- **Menos colores**: el color solo significa estado. Lima = hecho o victoria, ámbar = pendiente o convocatoria abierta, rojo = derrota; la competición va solo en su etiqueta (SNP/LAPI) y la fecha es neutra. Se quita la «E» del banner de la ficha.
- **Inicio**: la tarjeta abre con una línea de texto plano, «Próximo enfrentamiento · LAPI · Playoffs», sin etiquetas de color, y la pista 2:1 se ve también cuando no hay panel «Pendiente» (ancho máximo 820 px).
- **Ficha**: los convocados se ven primero y los suplentes quedan tras «Ver suplentes».
- **Listado para jugadores**: el recorrido de pasos solo lo ve el capitán o gestor; a los jugadores se les muestra una tarjeta como la de Inicio: fecha en grande, local contra visitante, estado y borde con el color de la competición.
- **Tarjeta del listado**: una fila por enfrentamiento con fecha en bloque neutro, competición, píldora de tipo («Liga», «Jornada N»…) y recorrido de cuatro pasos (Convoc. · Parejas · Result. · Acta) con ✓ hecho y «!» actual, calculado por `MatchPhase.track`. El marcador grande y el estado van a la derecha; en móvil, debajo.

## 30/10/2026 · Nuevo estilo visual (fase 1: base e Inicio)

- **Tipografía**: los títulos pasan a Anton (condensada, deportiva, en mayúsculas y sin cursiva); el cuerpo sigue en Archivo. El logotipo y la portada pública conservan Syncopate. Anton va en `static/zyra/fonts/` (licencia OFL).
- **Cabecera**: como el mockup. Escudo en círculo, pestañas solo con texto (sin iconos ni mayúsculas) con la activa en lima sin brillo, y botones de idioma y usuario en píldora plana. Con un solo equipo el botón de usuario dice «Nombre · Rol».
- **Barra móvil**: oscura, con el lima reservado a la pestaña activa.
- **Inicio**: el próximo enfrentamiento es un bloque lima con la fecha enorme, un indicador de días de fondo oscuro y los equipos local y visitante a cada lado de la red. En escritorio, junto a «Pendiente», el bloque es una pista de pádel de proporción 2:1 (nunca se deforma).
- **Pendiente**: panel propio con su contador y el botón «+ Nuevo»; las filas son una lista plana.
- **Equipos**: el banner grande «Tus equipos» pasa a una tira compacta con cada equipo (escudo, competición, rol y categoría).
- **En racha** desaparece del Inicio (la racha de cada jugador y pareja sigue en sus estadísticas). «Registra tu cuenta de SNP» es un aviso como el del gestor, junto a él.
- **Mi forma**: cuatro zonas (balance en anillo, últimos partidos con la racha, «te apuntaste → jugaste» y puntos SNP con su gráfica).

## 30/10/2026 · Espacios por competición (pendientes de la auditoría, PR #210)

- **Plantilla, Club y Rivales**: con rol mixto (gestionas un equipo y juegas en otro) la página dice «Equipo: X · LAPI» en vez de no mostrar nada.
- **Enfrentamientos**: el filtro de rival tiene etiqueta visible y «Quitar el rival» solo quita el rival (mantiene temporada y tipo). Al crear uno de liga se propone la jornada siguiente; la hora es un campo de 24 h (escribe 2030 y queda 20:30).
- **Poner resultados (SNP)**: la pregunta es «¿Se presentaron las dos parejas?» y, al marcar una pareja no presentada, se ve el reparto previsto de puntos (normativa 20.2) antes de cerrar el acta.
- **Reabrir acta**: también pueden el capitán y los gestores (queda anotado quién).
- **Convocatoria**: una ficha copiada que aún no aceptó la invitación se puede convocar y sale «Pendiente de aceptar».
- **Informes**: los datos de otras competiciones solo se incluyen si todos los que reciben el informe gestionan también ese otro equipo.
- **Filtros**: Competición, Temporada y Tipo son desplegables en una sola fila (con el rival en el listado); cada uno dice su valor y se marca en lima si no es «Todas». El panel lateral de Estadísticas › Equipo aparece desde 1024 px.
- **Mis estadísticas**: con dos equipos y sin ficha enlazada la pestaña explica cómo enlazarla.
- **Inicio › En racha**: con varios equipos, cada competición tiene su bloque (SNP y LAPI por separado).
- **Enfrentamientos y estadísticas**: el selector de enfrentamientos competitivos es un desplegable igual que Competición, Temporada y Tipo.
- **Gestionar plantilla**: arriba dice de qué equipo es la plantilla que editas.
- **Jugadores**: el aviso «Cópialos en vez de crearlos a mano» sale en ambos sentidos (SNP → LAPI y LAPI → SNP) y desaparece en cuanto se copia un jugador.
- **Mis estadísticas**: la tarjeta de sets explica cada dato dentro de la propia tarjeta, bajo su nombre (set decisivo, tie-breaks…) y, con una temporada elegida, se ve la gráfica de convocatorias de esa temporada (barras por competición).
- **Colores SNP/LAPI**: en Mis estadísticas cada competición tiene su marco (tinte suave y línea superior de su color) y los datos van en lima; las gráficas comparativas mantienen dorado y turquesa para distinguir series.

## 30/10/2026 · Espacios por competición (selectores, datos y zonas grises)

- **Inicio**: «Ver los N pendientes» indica cuántos tienen la fecha pasada; el capitán ve «Pon la categoría» (enlace a editar el equipo) cuando falta.
- **Estadísticas**: la ficha de jugador muestra la competición en el título; «Ver pareja» solo se activa al elegir los dos jugadores.
- **Avisos**: la preferencia del correo de resultado dice que vale para todos tus equipos; la página de advertencias dice de qué equipo son.

## 30/10/2026 · Espacios por competición (revisión de usabilidad, prioridades 2 y 3, PR #209)

- **Convocatoria**: con la convocatoria abierta la web dice «apuntados» y «Te has apuntado»; «convocados» y «Estás convocado» solo cuando está cerrada. «Cerrar convocatoria» y «Reenviar informe» piden confirmación y dicen a qué correos se envía. En Playoffs y Fase final, la regla de los 2 enfrentamientos de liga se ve en la ficha, se vuelve a comprobar al cerrar y separa a los apuntados que no la cumplen del resto.
- **Advertencias**: una sola palabra en todos los textos («Advertencias y cambios», «Poner advertencia»).
- **Menú «Más»** de la ficha agrupado en Convocatoria, Resultado especial y Enfrentamiento. Los textos de «No presentado» dicen lo que pasa en cada competición (SNP 12-0; LAPI 3-0 y puntos de liga).
- **Poner resultados**: un partido por fila con los nombres enteros; «Guardar y cerrar acta» se activa cuando están todos los resultados y dice cuántos faltan; el error nombra los partidos que faltan. La ayuda de lesión solo sale al marcar la casilla.
- **Alinear parejas**: nombre corto y posición en el selector, «Vaciar pareja», y la alineación sugerida dice cuántos enfrentamientos de historial la respaldan.
- **Selector de convocatoria**: «Jugó 2/3 esta temporada», «Mínimo 6 cumplido», «Marcar todos los de la lista» y «Ver solo elegidos».
- **LAPI**: sin «· 1 pts» en cada partido ni empates en el balance, el listado y Rivales.
- **Listado**: en móvil, temporada, tipo y rival van plegados tras «Filtros»; las etiquetas se llaman Temporada y Tipo; el filtro de competición recordado se ve en la cabecera con «Ver todas»; sin papelera en cada tarjeta; «Eres jugador aquí» solo si gestionas otro equipo.
- **Inicio**: «Próximo enfrentamiento» muestra tipo y jornada; el aviso del gestor dice de qué equipo habla y no sale si ya tiene uno; «Mi forma» y «Mis estadísticas» usan las mismas palabras.
- **Estadísticas**: «Juegos en casa: 59 ganados · 60 perdidos», «Roscos: 0 a favor · 0 en contra», muestras pequeñas avisadas, y una nota en Equipo, Jugador, Parejas y Rivales de por qué no hay «Todas».
- **Menú de usuario**: «Estás en:» presenta tus equipos como texto, no como opciones.
- **Plantilla y copiar jugadores**: «Copiado de SNP» pasa a la ficha del jugador; primero salen los que se pueden copiar y, si no hay nadie, el aviso va arriba y la lista queda plegada.
- **Colores**: SNP dorado (#DBA400), LAPI turquesa (#61E2C9) y el lima queda para Zyra (acción, activo, victoria).

## 30/10/2026 · Espacios por competición (revisión de usabilidad, prioridad 1, PR #208)

- Los enlaces de gestión (convocatoria, parejas, resultados, jugadores, advertencias…) abren siempre el **equipo correcto**, aunque en otra pestaña hayas cambiado de equipo. Si en ese equipo no tienes permiso, el aviso dice de qué equipo es y qué papel tienes.
- **Advertencias** solo la ven el capitán y los gestores, y solo de los equipos que gestionan.
- **Nuevo enfrentamiento** pregunta en qué equipo crearlo si eres capitán o gestor de varios; el formulario dice «Se creará en …» con un enlace para cambiar de equipo.
- La web habla de **equipo** en vez de «club» (menú, registro, miembros, abandonar…).
- Un mismo **estado** para cada enfrentamiento en el listado, el calendario, el Inicio y su página: «Por convocar», «Convocatoria abierta», «Por alinear», «Faltan 2 resultados», «Acta por cerrar», «Acta cerrada». Los avisos de progreso explican cada número («Faltan 2 apuntados para cerrar la convocatoria (8 de 10)»).
- **Mi perfil** muestra tu ficha en cada equipo («Mis fichas»), y la barra inferior del móvil dice «Enfrentamientos».

## 29/10/2026 · Espacios por competición (informe mensual por equipo y normativa SNP)

- El **informe mensual** llega en un solo correo con un PDF por cada equipo en el que jugaste ese mes (SNP y LAPI), cada uno con su competición en la cabecera. El de LAPI no lleva la gráfica de puntos SNP.
- **No presentado** también en SNP: el equipo que no se presenta pierde 12-0 (normativa SNP 20.3).
- **Lesión** en SNP como en LAPI: se elige la pareja lesionada y Zyra completa el partido para la sana (normativa 15.10).
- **Pareja no presentada** en SNP: en «Poner resultados», «¿Se jugó?» marca qué pareja no vino. Al cerrar el acta Zyra reparte los puntos como dice la normativa 20.2 (6 puntos para el cumplidor y 2/2/1/1 en los partidos jugados; dos parejas, 0-12; la misma pareja en los dos equipos, partido anulado).

## 29/10/2026 · Espacios por competición (fase 2: copiar jugadores entre SNP y LAPI)

- En Plantilla, **«Copiar de SNP»** (o de LAPI) trae jugadores de tu equipo de la otra competición si eres capitán o gestor en los dos. Se copian nombre, apellidos, foto y posición; las estadísticas, los puntos SNP y las convocatorias se quedan donde estaban.
- Los que ya tienen cuenta reciben una **invitación** por correo y en su Inicio; se les puede convocar antes de que acepten. Si la rechazan, la ficha queda sin cuenta y puedes borrarla.
- Las fichas de una misma persona comparten nombre, apellidos y foto: si los cambia en un equipo, cambian en todos. La posición es de cada equipo.
- En LAPI, Zyra avisa si la plantilla pasa de 15 jugadores, sin impedirlo.
- En «Completar equipo», la columna **«¿Es el mismo jugador?»** deja decir que un nombre de SNP es un jugador que ya tienes (por ejemplo, copiado de LAPI) para no crear otra ficha.
- En Mi perfil, si te copiaron a otro equipo antes de tener cuenta, puedes enlazar esa ficha («Sí, enlazarla») o decir «No es mía».
- Aunque solo tengas un equipo, cada enfrentamiento (listado, calendario, Inicio y su página) lleva la etiqueta de su competición, SNP o LAPI.
- El menú de usuario dice directamente **«Añadir equipo LAPI»** (o SNP) en vez de «Añadir equipo de otra competición», y abre el registro con esa competición elegida.

## 29/10/2026 · Espacios por competición (fase 1c: no presentados y lesiones en LAPI)

- **No presentado**: en un enfrentamiento LAPI con el acta abierta, «Más» › «No se presentó el rival» o «No nos presentamos» lo cierra con 3-0 para quien sí se presentó. Cuenta en el balance del equipo y en los puntos de liga (4 o 0), pero no en jugadores, parejas ni asistencia. Se puede quitar con «Quitar no presentado».
- **Lesión en LAPI**: al marcar «Partido finalizado por lesión» se elige la pareja lesionada y Zyra completa el partido para la sana (3-2 queda 3-6 / 0-6), con la vista previa en el formulario.
- En LAPI, Estadísticas ya no muestra «Por número de partido» ni «Balance de partidos por jugador»: el orden de los partidos lo decide el sorteo.
- La lesión también se marca en «Poner resultados», partido a partido, y la etiqueta «Lesión» dice qué pareja se lesionó. Al editar una lesión ya guardada la vista previa ya no da error con los sets 0-6.
- Si eres jugador en todos tus equipos, en Estadísticas › Jugador ves las estadísticas de tus compañeros, pero sin la pestaña «Resumen» de la ficha de Plantilla, que es de la vista de capitán.

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

## 28/10/2026 · Estadísticas por temporadas

- El buscador de temporadas lleva flecha para desplegar la lista completa.
- (Al volcar la rama de espacios a `main`: «Enfrentamientos ganados por año» con ventana «Antes / Después» sigue fuera de Estadísticas › Equipo, como en el rediseño de la fase 3.)

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
