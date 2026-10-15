# 01 · Hallazgos de UX, IA, UI y accesibilidad

Auditoría del 15/10/2026 sobre `main` (tras el PR #153), con la app arrancada en local
(`DJANGO_DEBUG=True python manage.py runserver`) y los datos de `populate_db.py`
(club LOS GLADIADORES, 23 jugadores, 14 equipos, 15 enfrentamientos). Cuentas de prueba:
capitán `edu`, miembro `jugador` (enlazado a un jugador) y `nuevo` (sin club).
Ver el método y lo que quedó fuera en [07-audit-coverage.md](07-audit-coverage.md).

## Cómo leer cada hallazgo

- **Confianza / tipo de evidencia**
    - **C1 · Confirmado**: observado en el navegador (Playwright + Chromium) o reproducido.
    - **C2 · Inspección**: deducido del código o de la plantilla, sin ejecutarlo.
    - **C3 · Hipótesis**: hay que validarlo con usuarios (ver [05](05-usability-testing-plan.md)).
    - **C4 · Oportunidad**: criterio profesional, no un fallo.
- **Severidad** (impacto, no facilidad): Crítica · Alta · Media · Baja.
- **Prioridad orientativa** = Impacto × Frecuencia × Importancia de la tarea × Confianza en la
  evidencia (cada factor de 1 a 5; resultado de 1 a 625). Sirve para comparar, no para medir.
- **Esfuerzo**: XS (< 2 h) · S (≤ 1 día) · M (2-4 días) · L (1-2 semanas) · XL (> 2 semanas).
- Capturas en la carpeta `capturas/` de este directorio. Las rutas de archivo se refieren a la raíz del repositorio.

No se ha encontrado ningún problema **crítico**: todas las tareas esenciales se pueden completar.
Los problemas más graves son de **arquitectura de información y eficiencia** del flujo semanal
del capitán, no de pantallas rotas.

## Resumen por prioridad

| ID | Título | Categoría | Sev. | Prioridad | Esfuerzo | Conf. |
|---|---|---|---|---|---|---|
| H-01 | «Partido» significa dos cosas distintas | Arquitectura de información | Alta | 500 | M | C1 |
| H-02 | El inicio no avisa de lo que está pendiente | Información faltante | Alta | 400 | M | C1 |
| H-04 | Poner los 5 resultados exige 10 cargas de página | Eficiencia | Alta | 400 | M | C1 |
| H-03 | La página del partido no indica el siguiente paso | Usabilidad | Alta | 320 | M | C1 |
| H-06 | El miembro no ve si está convocado ni con quién juega | Información faltante | Alta | 320 | M | C1/C3 |
| H-05 | La disponibilidad de los jugadores vive fuera de la app | Oportunidad de producto | Alta | 300 | L | C3 |
| H-08 | El feedback tras guardar depende de la pantalla | Errores e inconsistencias | Media | 300 | S | C1 |
| H-11 | Crear partido: dos ejes de tipo, sin hora ni lugar | Usabilidad | Media | 300 | M | C1 |
| H-13 | Barra inferior sin textos y en otro orden | Navegación | Media | 300 | S | C1 |
| H-29 | El selector de convocatoria no da datos para decidir | Eficiencia | Media | 300 | S | C1 |
| H-09 | Mensaje contradictorio tras cerrar la convocatoria | Errores e inconsistencias | Media | 240 | XS | C1 |
| H-10 | «Cerrar convocatoria»: rojo, sin aviso de email, sin bloqueo previo | Usabilidad | Media | 240 | S | C1 |
| H-20 | Nombres de jugador truncados y ambiguos | UI y jerarquía visual | Media | 240 | S | C1 |
| H-31 | Alineación en móvil: el orden de juego queda al final | Responsive | Media | 240 | M | C1 |
| H-14 | Miembros, invitaciones y SNP escondidos en el menú de cuenta | Navegación | Media | 180 | S | C1 |
| H-15 | Estadísticas de equipo: 8.900 px en móvil | Arquitectura de información | Media | 180 | M | C1 |
| H-16 | Estadísticas: el mismo balance tres veces y un gráfico engañoso | Información duplicada | Media | 180 | S | C1 |
| H-17 | Temporada por defecto distinta en cada pantalla | Errores e inconsistencias | Media | 180 | XS | C1 |
| H-21 | El resumen del partido no dice si se ganó | Información faltante | Media | 180 | XS | C1 |
| H-22 | «Primeros pasos» empuja el próximo partido fuera de la pantalla | UI y jerarquía visual | Media | 180 | S | C1 |
| H-40 | Al cerrar el acta se vuelve al listado sin resumen | Errores e inconsistencias | Media | 180 | S | C1 |
| H-18 | Formatos de puntos SNP y fechas mezclados | UI y jerarquía visual | Baja | 150 | S | C1 |
| H-07 | Sanciones: tres nombres, sin motivo y sin deshacer | Usabilidad | Alta | 120 | M | C1/C2 |
| H-19 | Cuatro paginaciones distintas (4, 9, 12 y 20 por página) | Errores e inconsistencias | Media | 120 | S | C1 |
| H-30 | A 320 px las barras fijas tapan el contenido | Responsive | Media | 120 | S | C1 |
| H-25 | Datos del jugador repartidos en tres pantallas | Información duplicada | Media | 108 | M | C1 |
| H-27 | El foco de teclado queda bajo la barra inferior | Accesibilidad | Media | 108 | XS | C1 |
| H-12 | La validación de «Crear partido» usa la burbuja del navegador | Usabilidad | Media | 96 | S | C1 |
| H-28 | Objetivos táctiles pequeños (lápiz de fecha 13×14 px) | Accesibilidad | Baja | 72 | XS | C1 |
| H-38 | El equipo propio aparece mezclado con los rivales | Arquitectura de información | Baja | 72 | M | C1 |
| H-23 | En «Miembros» se cambia el email sin contraseña | Errores e inconsistencias | Alta | 64 | XS | C2 |
| H-35 | Registro de cambios de la convocatoria difícil de leer | Información faltante | Baja | 60 | S | C1/C2 |
| H-36 | Se puede cerrar el acta de un partido futuro | Errores e inconsistencias | Media | 60 | XS | C1 |
| H-26 | «Peores parejas» a la vista de todo el club | Oportunidad de producto | Media | 54 | S | C3 |
| H-33 | Alta de club: 14 campos en una sola pantalla | Usabilidad | Media | 45 | M | C3 |
| H-24 | «Mi perfil» enseña a los miembros una preferencia de capitán | Información duplicada | Baja | 40 | XS | C1 |
| H-32 | Lema en inglés en la portada en español | UI y jerarquía visual | Baja | 25 | XS | C1 |
| H-37 | «Ver estadísticas» del jugador en racha solo para el capitán | Errores e inconsistencias | Baja | 20 | XS | C2 |
| H-39 | Mayúsculas, dos puntos y títulos sin criterio único | UI y jerarquía visual | Baja | 20 | XS | C1 |
| H-34 | Selector de archivo nativo sin estilo ni idioma de la página | UI y jerarquía visual | Baja | 12 | XS | C3 |

Los hallazgos H-07 y H-23 tienen severidad Alta aunque su puntuación es baja: el primero
deja datos que no se pueden corregir y el segundo es un riesgo de seguridad. La fórmula no
recoge ese riesgo, así que se priorizan aparte (ver [06-improvement-roadmap.md](06-improvement-roadmap.md)).

---

## Arquitectura de información y terminología

### H-01 · «Partido» significa dos cosas distintas

- **Categoría**: Arquitectura de información · **Severidad**: Alta · **Prioridad**: 500 (4×5×5×5)
- **Pantallas**: menú «Partidos», `/match/call_for_match/<id>/`, `/match/create_game/<id>/`,
  `/data_analyse/team_statistics`.
- **Tarea afectada**: todas las del ciclo del partido; explicar la app a un jugador nuevo.
- **Evidencia (C1)**: el menú «Partidos» y el botón «Nuevo partido» se refieren al
  enfrentamiento entre equipos. Dentro de esa página, la sección «Partidos» lista «Partido 1 · 3 pts»
  … «Partido 5», y el botón «Crear partidos» crea las cinco parejas
  ([captura](capturas/escritorio-partido-acta-cerrada.jpg)). Las estadísticas mezclan los dos
  sentidos: «Partidos ganados 50 %» (enfrentamientos), «Racha de victorias: 5 enfrentamientos»,
  «Por número de partido» (parejas). El modelo ya distingue `Match` y `Game` (`match/models.py`),
  y la interfaz los llama igual.
- **Problema**: el usuario no puede saber por el texto si una acción afecta a la jornada entera
  o a una pareja. «Crear partidos» dentro de un partido es una contradicción.
- **Consecuencia**: errores de interpretación en estadísticas («¿he ganado el 57 % de
  partidos o de enfrentamientos?»), dificultad para explicar la app, ayuda contextual imposible.
- **Recomendación**: un término por concepto y en todas partes (textos, títulos, botones,
  estadísticas, PDF, traducción inglesa).
    - Opción A (recomendada): **Enfrentamiento** para el `Match` (es el término de SNP y ya se
      usa en récords y en el tipo «Enfrentamiento»), **Partido 1-5** para cada `Game`. Menú
      «Enfrentamientos» en escritorio y «Jornadas» o «Partidos» con icono en la barra móvil si
      no cabe. «Nuevo enfrentamiento», «Crear partidos» pasa a «Alinear parejas».
    - Opción B: **Partido** para el `Match` y **Pista 1-5** para cada `Game`.
    - Los amistosos encajan en la opción A como «Enfrentamiento amistoso» o simplemente
      «Amistoso».
- **Esfuerzo**: M (textos, `locale/en/LC_MESSAGES/django.po`, PDF en `match/report_pdf.py`, guías).
- **Dependencias**: decisión de producto (opción A o B); validar con 2-3 capitanes (tarea T6 del plan).
- **Validación**: prueba de comprensión de 5 segundos sobre la página del partido; métrica:
  % de participantes que explican bien qué es «Partido 3».

### H-14 · Miembros, invitaciones y Cuenta SNP escondidos en el menú de cuenta

- **Categoría**: Navegación · **Severidad**: Media · **Prioridad**: 180 (3×3×4×5)
- **Pantallas**: cabecera (`core/templates/base.html`), botón con el nombre del club.
- **Tarea afectada**: invitar a jugadores, configurar SNP, traspasar capitanía.
- **Evidencia (C1)**: «Miembros del club» y «Cuenta SNP» solo aparecen en el desplegable cuyo
  botón muestra el nombre del club; ese mismo menú contiene «Mi perfil», «Abandonar el club»,
  «Back-office» y «Cerrar sesión». En móvil el botón es solo un icono de usuario. El paso
  «Invita a tus jugadores» de «Primeros pasos» es el único acceso visible.
- **Problema**: se mezcla la configuración del club (de todos) con la cuenta personal, y el
  botón que la abre se etiqueta con el nombre del club, no como «cuenta».
- **Consecuencia**: el capitán que ha ocultado «Primeros pasos» no encuentra cómo invitar a
  alguien nuevo a mitad de temporada.
- **Recomendación**: crear una sección **Club** en la navegación principal (ver
  [02-information-architecture.md](02-information-architecture.md)) con Miembros e invitaciones,
  Mi equipo, Rivales y Cuenta SNP. El menú de cuenta queda en: Mi perfil, idioma, Cerrar sesión
  (y Back-office para personal).
- **Esfuerzo**: S (una página índice + mover enlaces) · **Dependencias**: H-13, H-38.
- **Validación**: tarea T5 del plan («invita a un jugador nuevo»); tiempo hasta el primer clic correcto.

### H-15 · Estadísticas de equipo: 8.900 px en móvil

- **Categoría**: Arquitectura de información · **Severidad**: Media · **Prioridad**: 180 (3×4×3×5)
- **Pantalla**: `/data_analyse/team_statistics`.
- **Evidencia (C1)**: alto medido 5.100 px en escritorio, 6.981 px en tablet, 8.920 px a 390 px y
  10.307 px a 320 px. La ficha de un jugador mide 6.115 px en móvil con 18 bloques. El informe
  de usabilidad del 09/10 medía unos 17.000 px: ha mejorado, pero sigue siendo una sola página con
  Top 5, Partidos y sets, Récords, Gráficos y Puntos SNP seguidos
  ([captura](capturas/escritorio-estadisticas-equipo.jpg)).
- **Problema**: no hay forma de saltar a una sección ni de ver de un vistazo qué contiene la
  página; lo que más se consulta (balance y mejores parejas) compite con detalle avanzado
  (remontadas, roscos, sets ajustados).
- **Recomendación**: subpestañas ancladas o un índice fijo bajo el título: **Resumen** (balance +
  forma reciente + 3 récords) · **Jugadores** · **Parejas** · **Partidos y sets** · **SNP**. Abrir
  por defecto «Resumen». Las secciones ya tienen `scroll-margin-top` (`.st-section` en
  `static/style.css`), así que el índice con anclas es barato.
- **Esfuerzo**: M · **Dependencias**: H-16, H-17.
- **Validación**: métrica de scroll profundo (eventos de sección vista) y tarea T4.

### H-25 · Datos del jugador repartidos en tres pantallas

- **Categoría**: Información duplicada · **Severidad**: Media · **Prioridad**: 108 (3×3×3×4)
- **Pantallas**: `/players/player_details/<id>/` (ficha), `/data_analyse/player_statistics?player=<id>`
  (estadísticas), `/players/edit_player/<id>` y `/players/roster/` (pertenencia al equipo).
- **Evidencia (C1)**: la ficha muestra posición, mano, puntos SNP y «Últimos partidos» con una
  letra V/D sin marcador ([captura](capturas/escritorio-jugadores.jpg)); las estadísticas del mismo
  jugador están en otra sección del menú. «En el equipo» se cambia en la edición del jugador
  (`players/forms.py`, campo `in_team`) y en «Gestionar plantilla».
- **Problema**: el usuario tiene que saber que la ficha no es «el jugador» completo; desde
  Estadísticas no se llega a la ficha ni a editarlo.
- **Recomendación**: una sola ficha de jugador con pestañas **Resumen** (lo de hoy + forma reciente)
  y **Estadísticas** (la página actual de estadísticas por jugador). «Estadísticas › Jugador» pasa
  a ser un buscador que abre esa ficha. Mantener «Gestionar plantilla» (edición en lote útil) pero
  quitar `in_team` del formulario individual o mostrarlo como interruptor con la misma etiqueta.
- **Esfuerzo**: M · **Dependencias**: ninguna · **Validación**: tarea T4 (encontrar la racha de un jugador).

### H-38 · El equipo propio aparece mezclado con los rivales

- **Categoría**: Arquitectura de información · **Severidad**: Baja · **Prioridad**: 72 (2×3×3×4)
- **Pantalla**: `/team/list_teams` ([captura móvil](capturas/movil-equipos.jpg)).
- **Evidencia (C1)**: LOS GLADIADORES sale en la lista de «Equipos» entre ATLÉTICO ISLEÑO y
  NORTHPADEL, con la misma tarjeta y el mismo lápiz. El listado pagina de 4 en 4
  (`team/views.py`, `Paginator(teams, 4)`).
- **Problema**: «Equipos» mezcla la configuración del club (foto, ubicación, categoría del equipo
  propio) con el catálogo de rivales, que solo sirve para crear partidos.
- **Recomendación**: mover el equipo propio a **Club › Mi equipo** y renombrar la lista a
  **Rivales** (en Club, ver [02](02-information-architecture.md)). Subir la página a 12-24 elementos.
- **Esfuerzo**: M · **Dependencias**: H-14.

## Información faltante y estados

### H-02 · El inicio no avisa de lo que está pendiente

- **Categoría**: Información faltante · **Severidad**: Alta · **Prioridad**: 400 (4×4×5×5)
- **Pantalla**: `/` con club (`core/views.py`, `home`; `core/templates/home.html`).
- **Tarea afectada**: retomar el trabajo de la semana (convocar, alinear, cerrar acta).
- **Evidencia (C1)**: el enfrentamiento del 4 de octubre contra ATLÉTICO ISLEÑO no tiene
  convocatoria ni resultado. Hoy (15/10) el inicio dice «No hay partidos programados» y ofrece
  «Crear partido» ([captura](capturas/escritorio-inicio-capitan.jpg)). La vista solo busca
  `start_date__gte=today`. El listado sí lo marca como «Sin resultado».
  Al revés, un enfrentamiento futuro con el acta ya cerrada sale como «Próximo partido» con el botón
  «Ver convocatoria» ([captura del miembro](capturas/movil-inicio-miembro.jpg)).
- **Problema**: el inicio enseña la agenda pero no las tareas; lo que se ha quedado a medias
  desaparece justo cuando hay que terminarlo.
- **Consecuencia**: actas sin cerrar que no cuentan en estadísticas; el capitán puede crear un
  partido duplicado en vez de terminar el que ya existe.
- **Recomendación**: bloque **«Pendiente»** arriba del inicio para capitanes, con una fila por
  enfrentamiento abierto y su siguiente acción: «Convocar» (sin convocatoria), «Cerrar
  convocatoria (8/10)», «Alinear parejas», «Poner resultados (3/5)», «Cerrar acta». Ordenado por
  fecha; los pasados en rojo. Debajo, «Próximo partido» solo con actas abiertas. Si no hay nada
  pendiente: «Todo al día».
- **Esfuerzo**: M (consulta por estado + plantilla) · **Dependencias**: H-03 (mismo cálculo de estado).
- **Validación**: % de enfrentamientos pasados con acta abierta a los 7 días (medible hoy en BD);
  tarea T2.

### H-06 · El miembro no ve si está convocado ni con quién juega

- **Categoría**: Información faltante · **Severidad**: Alta · **Prioridad**: 320 (4×5×4×4)
- **Pantalla**: inicio del miembro ([captura](capturas/movil-inicio-miembro.jpg)).
- **Evidencia (C1)**: el inicio del miembro muestra el próximo partido, «Jugador en racha» y
  «Pareja en racha». No dice si su jugador está convocado, en qué pareja ni en qué partido juega,
  aunque la cuenta está enlazada a un jugador (`Player.user`). Para saberlo hay que abrir el
  partido y buscar su nombre entre chips truncados (H-20).
- **Problema**: el rol miembro es «solo lectura» y la pregunta que se hace un jugador cada semana
  («¿juego?, ¿con quién?, ¿a qué hora?») no tiene respuesta directa.
- **Consecuencia (C3)**: los jugadores siguen dependiendo del WhatsApp del capitán y entran poco;
  sin uso de miembros, invitar tiene poco valor.
- **Recomendación**: tarjeta **«Tu próximo partido»** para cuentas enlazadas: «Estás convocado» /
  «No estás convocado», y tras alinear «Partido 2 con ANTONIO URRACO · 3 pts». Resaltar su chip en
  la página del partido. Sin jugador enlazado: invitación a enlazarse.
- **Esfuerzo**: M · **Dependencias**: H-05 si se añade disponibilidad.
- **Validación**: entrevistas con 2-3 jugadores (T7); visitas semanales de miembros.

### H-05 · La disponibilidad de los jugadores vive fuera de la app

- **Categoría**: Oportunidad de producto · **Severidad**: Alta · **Prioridad**: 300 (5×4×5×3)
- **Pantallas**: crear convocatoria, inicio del miembro.
- **Evidencia**: (C2) no hay ningún modelo ni pantalla de disponibilidad; la convocatoria se hace
  marcando nombres sin información de quién puede ir. (C3) el propio texto de la portada y el
  flujo hacen suponer que el capitán pregunta por WhatsApp y después lo copia.
- **Problema**: el paso que más tiempo cuesta al capitán (saber quién puede) ocurre fuera, y la
  app recibe solo el resultado.
- **Recomendación**: petición de disponibilidad por enfrentamiento: el capitán la lanza al crear
  el partido (casilla «Preguntar disponibilidad»), cada miembro responde Sí / No / Duda desde un
  enlace o desde el inicio, y el selector de convocatoria muestra el estado y ordena primero a los
  disponibles. Spond y TeamSnap resuelven así el mismo problema (ver
  [03](03-user-flows-and-shortcuts.md#benchmark)).
- **Riesgos**: solo aporta si los jugadores tienen cuenta; hoy muchos jugadores son fichas sin
  cuenta. Necesita correo o enlace sin sesión (como `core/unsubscribe.py`).
- **Esfuerzo**: L · **Dependencias**: H-06, envío de correo ya existente (`core/emails.py`).
- **Validación**: hipótesis H2 del plan de pruebas antes de construir; después, % de convocados
  con respuesta.

### H-21 · El resumen del partido no dice si se ganó

- **Categoría**: Información faltante · **Severidad**: Media · **Prioridad**: 180 (3×4×3×5)
- **Pantalla**: `/match/call_for_match/<id>/` con acta cerrada.
- **Evidencia (C1)**: el marcador «5/7» aparece sin la palabra Victoria / Derrota, aunque el
  listado ya muestra «DERROTA»; el título es siempre «Resumen del partido». Era la propuesta 2 del
  informe del 09/10 y sigue pendiente.
- **Recomendación**: reutilizar la etiqueta de estado de `match/templates/list_match.html` junto
  al marcador y titular con los equipos («LOS GLADIADORES – NORTHPADEL»), dejando «Resumen» como
  antetítulo.
- **Esfuerzo**: XS · **Validación**: test de 5 segundos (¿quién ganó?).

### H-35 · Registro de cambios de la convocatoria difícil de leer

- **Categoría**: Información faltante · **Severidad**: Baja · **Prioridad**: 60 (2×2×3×5)
- **Pantalla**: `/callLog/view_call_log/<id>` ([captura](capturas/escritorio-cambios-convocatoria-sanciones.jpg)).
- **Evidencia**: (C1) cada línea es texto libre: «Jugadores añadidos con la convocatoria abierta:
  JUAN, … el día 03-10-2026 18:22:10;». (C2) el texto se genera en español fijo y solo con el primer
  nombre (`match/views.py`, `edit_call`, `Player.name.upper()`), y la plantilla lo colorea buscando
  las subcadenas «convocatoria abierta» y «cerrada» (`callLog/templates/view_call_log.html`). En
  inglés no se traduce (problema ya listado en `ZYRA_CONTEXT.md`).
- **Recomendación**: guardar eventos estructurados (fecha, jugador, alta/baja, estado de la
  convocatoria) y pintarlos como lista con nombre corto completo y fecha legible. Separar el
  registro de la acción de sancionar (H-07).
- **Esfuerzo**: S (sin migrar el histórico: mostrar el texto antiguo tal cual).

## Usabilidad y flujo del partido

### H-03 · La página del partido no indica el siguiente paso

- **Categoría**: Usabilidad · **Severidad**: Alta · **Prioridad**: 320 (4×4×5×4)
- **Pantalla**: `/match/call_for_match/<id>/` (`match/templates/call_for_match.html`).
- **Tarea afectada**: ciclo completo crear → convocar → cerrar convocatoria → alinear →
  resultados → cerrar acta.
- **Evidencia (C1)**: recorrido completo ejecutado en móvil
  ([03](03-user-flows-and-shortcuts.md#f1-ciclo-semanal-del-capitan)). En cada estado cambia el
  juego de botones y su lugar: «Crear convocatoria» arriba a la derecha; después «Editar»,
  «Penalizaciones», «Informe PDF», «Reenviar informe» y «Cerrar convocatoria» en una fila; luego
  «Crear partidos» más abajo, «+» pequeños en cada partido y «Cerrar acta del partido» al final.
  El estado se expresa con tres insignias distintas: «Sin validar» (partido), «Abierta/Cerrada»
  (convocatoria) y «Acta cerrada».
- **Problema**: el capitán tiene que deducir en qué fase está y buscar el botón cada vez; el
  orden real (5 fases) no se ve en ningún sitio.
- **Recomendación**: un **indicador de fases** bajo el marcador: Convocatoria · Parejas ·
  Resultados · Acta, con la fase actual resaltada y **un único botón principal** «Siguiente:
  …» que siempre está en el mismo sitio (debajo del indicador en escritorio, barra fija sobre la
  navegación en móvil). Acciones secundarias (Editar convocatoria, Informe PDF, Reenviar,
  Sanciones) en un menú «Más». Una sola palabra de estado: «Borrador», «Convocado»,
  «Alineado», «Jugado», «Acta cerrada». Wireframe en [03](03-user-flows-and-shortcuts.md#propuesta-visual-2-pagina-del-partido).
- **Esfuerzo**: M · **Dependencias**: H-02 (comparte el cálculo de fase), H-04.
- **Validación**: tarea T1; errores de navegación (retrocesos) y tiempo.

### H-04 · Poner los 5 resultados exige 10 cargas de página

- **Categoría**: Eficiencia · **Severidad**: Alta · **Prioridad**: 400 (4×4×5×5)
- **Pantallas**: `/match/create_result/<game>/`, `/match/edit_result/<game>/`.
- **Evidencia (C1)**: en la prueba automatizada, introducir 5 resultados costó 10 navegaciones y
  31 interacciones (abrir, rellenar 4-6 casillas, guardar, volver). Tras cada guardado la página
  vuelve arriba del todo (`scrollY = 0`, el `redirect` de `_save_result` no lleva ancla) y no hay
  mensaje de confirmación, así que hay que bajar y buscar el siguiente «+»
  ([captura](capturas/movil-partido-con-parejas.jpg), [formulario](capturas/movil-resultado.jpg)).
- **Problema**: es la tarea que se hace siempre justo después de jugar, a menudo desde el
  móvil y con prisa.
- **Recomendación**: pantalla **«Resultados del enfrentamiento»** con los 5 partidos en una
  lista: 6 casillas por partido, validación en vivo que ya existe (`static/js/result-form.js`),
  marcador total calculado arriba y un solo «Guardar» (guarda los completos, deja los vacíos) +
  «Guardar y cerrar acta» cuando están los 5. Mantener el formulario individual para editar uno.
  Mínimo inmediato: redirigir a `#partido-<n>` y mostrar «Resultado del partido N guardado».
- **Ahorro**: de 10 a 1-2 cargas de página; de ~31 a ~24 interacciones (las casillas siguen).
- **Esfuerzo**: M (vista nueva que reutiliza `match/scoring.py`) · XS el mínimo inmediato.
- **Validación**: tarea T3: tiempo para introducir 5 resultados dados en papel; errores de validación.

### H-08 · El feedback tras guardar depende de la pantalla

- **Categoría**: Errores e inconsistencias · **Severidad**: Media · **Prioridad**: 300 (3×5×4×5)
- **Evidencia (C1)**: con mensaje: cerrar convocatoria («Convocatoria cerrada. Informe enviado
  a …»), crear partidos («Partidos creados.»), preferencias, cambiar fecha. **Sin mensaje**:
  crear partido, crear convocatoria, editar convocatoria, guardar resultado, aplicar sanción,
  cerrar acta (vuelve al listado sin nada), borrar partido.
- **Problema**: el usuario no sabe si la acción ha funcionado; en sanciones y resultados no hay
  ninguna otra pista visible.
- **Recomendación**: regla única: toda acción que guarda emite un `messages.success` breve con
  el objeto («Convocatoria creada con 12 jugadores», «Resultado del partido 3 guardado: 6-4 6-3»).
  Añadirlo a `docs/ai/business-rules.md` junto a la regla 12 de `ZYRA_CONTEXT.md` y comprobarlo con
  un test por vista.
- **Esfuerzo**: S · **Validación**: revisión con lista de vistas POST; test automatizado.

### H-09 · Mensaje contradictorio tras cerrar la convocatoria

- **Categoría**: Errores e inconsistencias · **Severidad**: Media · **Prioridad**: 240 (3×4×4×5)
- **Evidencia (C1)**: con la convocatoria ya cerrada, el bloque vacío de «Partidos» sigue diciendo
  «Todavía no hay partidos. Primero hay que cerrar la convocatoria.»
  ([captura](capturas/movil-partido-convocatoria-cerrada.jpg)); el texto no depende del estado en
  `match/templates/call_for_match.html`.
- **Recomendación**: tres textos según estado: sin convocatoria («Primero crea la convocatoria»),
  abierta («Cierra la convocatoria para alinear parejas») y cerrada («Ya puedes alinear las
  parejas» + botón).
- **Esfuerzo**: XS.

### H-10 · «Cerrar convocatoria»: rojo, sin aviso del correo y sin bloqueo previo

- **Categoría**: Usabilidad · **Severidad**: Media · **Prioridad**: 240 (3×4×4×5)
- **Evidencia (C1)**: el botón usa `btn-danger` aunque es el paso normal hacia delante. Con 3
  convocados se puede pulsar y aparece después el popup «Revisa esto: Para cerrar una convocatoria
  al menos debes contar con 10 jugadores» ([captura](capturas/movil-cerrar-convocatoria-con-3.jpg)).
  Al cerrar se envía el PDF a los capitanes (`_send_report`), cosa que el botón no anticipa.
- **Recomendación**: estilo primario; deshabilitado con texto «Faltan 7 convocados» por debajo
  de 10; subtítulo «Se enviará el informe PDF a: edu@…». Reservar el rojo para borrar.
- **Esfuerzo**: S.

### H-07 · Sanciones: tres nombres, sin motivo y sin deshacer

- **Categoría**: Usabilidad · **Severidad**: Alta · **Prioridad**: 120 (4×2×3×5)
- **Pantallas**: botón «Penalizaciones» del partido → `/callLog/view_call_log/<id>` («Cambios en la
  convocatoria» + «Aplicar sanciones») → pestaña «Advertencias» de Estadísticas.
- **Evidencia**: (C1) el mismo concepto (`Penalty`) se llama Penalizaciones, Sanciones y
  Advertencias según la pantalla. Al aplicar una sanción no hay mensaje y se vuelve al partido.
  (C2) `penalty/views.py` guarda un motivo fijo («Advertencia en el partido X VS Y.») sin campo
  para escribirlo, y no existe ninguna vista para borrar una sanción
  (no hay `delete` de `Penalty` fuera de los tests).
- **Problema**: un toque por error deja una advertencia permanente que se ve en el selector de
  convocatoria y en estadísticas, y no se puede corregir sin la base de datos.
- **Recomendación**: un nombre (**Advertencia**), motivo opcional con sugerencias («No avisó de
  la baja», «Llegó tarde»), confirmación con resumen y **deshacer** (borrar) desde la pestaña
  Advertencias para el capitán. Mover «Aplicar advertencia» a la página del partido (menú «Más»),
  separado del registro de cambios.
- **Esfuerzo**: M · **Validación**: revisión con capitanes (T8).

### H-11 · Crear partido: dos ejes de tipo, sin hora ni lugar

- **Categoría**: Usabilidad · **Severidad**: Media · **Prioridad**: 300 (3×4×5×5)
- **Pantalla**: `/match/create_match` ([captura](capturas/escritorio-crear-partido.jpg)).
- **Evidencia (C1)**: el formulario pide «Modo» (Competitivo / Amistoso) y, solo en competitivo,
  «Tipo de partido» (Enfrentamiento / Reto / Play Off): dos controles para una sola decisión. El
  equipo propio va siempre de local por defecto y, para jugar fuera, hay que cambiar las dos
  tarjetas, mientras que en el modo «Escribir nombre» existe el interruptor «Tu equipo juega como
  Local/Visitante». No hay hora ni lugar editable (el lugar se copia del local). «Datos del informe
  PDF» se pregunta aquí, días antes de que exista informe. No hay enlace para volver ni cancelar.
- **Recomendación**: (1) un único selector «Tipo»: Liga · Reto · Play Off · Amistoso; (2) «Rival»
  + interruptor «Jugamos en casa / fuera» en lugar de dos tarjetas; (3) hora opcional y lugar
  editable prerrellenado; (4) mover «Datos del informe» a la pantalla del informe o a «Más
  opciones» plegado; (5) enlace «Cancelar» a Partidos.
- **Ahorro**: de 7 campos y 7-9 interacciones a 3-4 campos obligatorios (rival, casa/fuera, fecha).
- **Esfuerzo**: M (hora y lugar requieren campo y migración) · **Dependencias**: H-01.
- **Validación**: tarea T1 (crear un partido fuera de casa); errores de equipo local/visitante.

### H-12 · La validación de «Crear partido» usa la burbuja del navegador

- **Categoría**: Usabilidad · **Severidad**: Media · **Prioridad**: 96 (3×2×4×4)
- **Evidencia (C1)**: al enviar sin rival, Chromium muestra su burbuja nativa («Please select an
  item in the list.» en un navegador en inglés) pegada al borde izquierdo y medio tapada, porque el
  `<select>` real es transparente y cubre la tarjeta ([captura](capturas/movil-crear-partido-validacion.jpg)).
  El idioma de la burbuja depende del navegador, no de la página.
- **Recomendación**: `novalidate` en el formulario y mensajes del servidor o de `static/js/match-form.js`
  bajo la tarjeta («Elige el equipo rival»), con la tarjeta en borde rojo y `aria-invalid`.
- **Esfuerzo**: S.

### H-29 · El selector de convocatoria no da datos para decidir

- **Categoría**: Eficiencia · **Severidad**: Media · **Prioridad**: 300 (3×4×5×5)
- **Pantalla**: `/match/create_call/<id>/`, `/match/edit_call/<id>/`
  ([captura](capturas/escritorio-crear-convocatoria.jpg)).
- **Evidencia (C1)**: cada tarjeta muestra nombre (truncado, H-20) y posición. Con 23 jugadores y
  20 por página, los 3 últimos están en otra página. Las advertencias de un jugador solo están en el
  atributo `title` del icono (`match/templates/includes/player_selector.html`): no se ven en móvil
  ni las anuncia un lector de pantalla. No hay puntos SNP, partidos jugados esta temporada, última
  convocatoria ni disponibilidad.
- **Recomendación**: mostrar por jugador SNP, «Jugó 6 de 8» y advertencias como texto visible;
  ordenar por disponibilidad (H-05) o por SNP; mostrar los 23 sin paginar (cabe: la plantilla
  típica es < 30) con filtros por posición ya existentes; acción rápida **«Repetir la última
  convocatoria»**.
- **Esfuerzo**: S (sin disponibilidad) · **Validación**: tarea T1, tiempo de convocatoria.

### H-31 · Alineación en móvil: el orden de juego queda al final

- **Categoría**: Responsive · **Severidad**: Media · **Prioridad**: 240 (3×4×5×4)
- **Pantalla**: `/match/create_game/<id>/` en móvil ([captura](capturas/movil-alineacion-sugerida.jpg)).
- **Evidencia (C1)**: al pulsar «Alineación sugerida» aparece un párrafo de unas 90 palabras con
  porcentajes; las 5 «Pareja N» ocupan unos 1.900 px y el bloque «Orden de juego» (lo que decide qué
  pareja juega el Partido 1) queda al final. La «Pareja 1» elegida puede acabar en el «Partido 3»
  porque el orden se recalcula por SNP. La barra fija «5 de 5 parejas · Guardar» tapa los campos de
  la primera pareja. Los puntos se muestran como «103281.3 pts» (punto decimal).
- **Recomendación**: en móvil, una lista única ordenada por partido (Partido 1 · 3 pts → pareja),
  editable en el sitio; la explicación de la sugerencia en una línea («94 % de opciones de ganar ·
  Ver por qué») desplegable; `padding-bottom` del contenido igual al alto de las barras fijas.
- **Esfuerzo**: M · **Dependencias**: H-01.

### H-40 · Al cerrar el acta se vuelve al listado sin resumen

- **Categoría**: Errores e inconsistencias · **Severidad**: Media · **Prioridad**: 180 (3×3×4×5)
- **Evidencia (C1)**: `close_match` redirige a `list_match` sin mensaje. El momento de cierre (el
  final de la tarea semanal) no confirma el resultado ni ofrece los siguientes pasos.
- **Recomendación**: quedarse en el partido con el mensaje «Acta cerrada: Victoria 7-5» y dos
  acciones: «Compartir resultado» (texto para WhatsApp con marcador y parejas) y «Ver
  estadísticas». Pedir confirmación con el marcador antes de cerrar.
- **Esfuerzo**: S.

### H-36 · Se puede cerrar el acta de un partido futuro

- **Categoría**: Errores e inconsistencias · **Severidad**: Media · **Prioridad**: 60 (3×1×4×5)
- **Evidencia (C1)**: el 15/10 se crearon partidos el 25/10 y el 1/11, con convocatoria,
  resultados y acta cerrada sin aviso. Después el inicio muestra ese partido como «Próximo
  partido» con «Ver convocatoria».
- **Recomendación**: avisar (no bloquear) al poner resultados antes de la fecha: «Este partido
  es el 1 de noviembre. ¿Cambiar la fecha a hoy?». El «Próximo partido» debe excluir actas
  cerradas.
- **Esfuerzo**: XS.

### H-33 · Alta de club: 14 campos en una sola pantalla

- **Categoría**: Usabilidad · **Severidad**: Media · **Prioridad**: 45 (3×1×5×3)
- **Pantalla**: `/core/register_club/` ([captura](capturas/escritorio-registro-club.jpg)).
- **Evidencia (C1)**: tres bloques (Club, Tu cuenta, Tu jugador) con nombre, localización,
  categoría, nacionalidad, división, usuario, email, contraseña ×2, opción SNP, nombre y
  apellidos, más un aviso de que deben coincidir con SNP. (C3) se desconoce la tasa de abandono.
- **Recomendación**: pedir solo lo imprescindible (nombre del club, cuenta, nombre del capitán);
  categoría, nacionalidad y división como paso posterior o rellenadas desde SNP cuando se conecta
  la cuenta. Medir antes el embudo (ya hay `DailyMetric` en el back-office).
- **Esfuerzo**: M · **Validación**: embudo registro → primer partido; tarea T9.

### H-26 · «Peores parejas» a la vista de todo el club

- **Categoría**: Oportunidad de producto · **Severidad**: Media · **Prioridad**: 54 (3×3×2×3)
- **Pantalla**: `/data_analyse/pair_statistics` ([captura](capturas/escritorio-estadisticas-parejas.jpg)).
- **Evidencia**: (C1) la lista «Peores parejas» muestra nombres con 0 % sobre 2 partidos.
  (C2) la vista solo exige pertenecer al club (`club_required`), así que la ven los miembros.
- **Hipótesis (C3)**: en un equipo amateur, un ranking negativo visible para todos con muestras
  tan pequeñas puede molestar más que ayudar.
- **Recomendación**: validar con capitanes; opciones: visible solo para el capitán, mínimo de 4
  partidos o renombrar a «Parejas por mejorar».

## Navegación, UI y responsive

### H-13 · Barra inferior sin textos y en otro orden

- **Categoría**: Navegación · **Severidad**: Media · **Prioridad**: 300 (3×5×4×5)
- **Evidencia (C1)**: escritorio: Inicio · Partidos · Jugadores · Equipos · Estadísticas. Móvil:
  Inicio · Estadísticas · Partidos · Equipos · Jugadores, solo iconos (el texto es
  `visually-hidden`). Por debajo de 992 px (tablets incluidas) se usa la barra de móvil aunque
  sobra espacio ([captura tablet](capturas/tablet-inicio.jpg)). Era la propuesta 13 del 09/10.
- **Recomendación**: mismo orden en las dos (el del flujo: Inicio · Partidos · Plantilla ·
  Estadísticas · Club, ver [02](02-information-architecture.md)) y etiqueta corta visible bajo cada
  icono (11-12 px).
- **Esfuerzo**: S.

### H-20 · Nombres de jugador truncados y ambiguos

- **Categoría**: UI y jerarquía visual · **Severidad**: Media · **Prioridad**: 240 (3×4×4×5)
- **Evidencia (C1)**: chips de la convocatoria en móvil («DANIEL CARRAT…», «ALBERTO MONT…»),
  «Gestionar plantilla» en escritorio a 4 columnas («ALBERTO CA…» / «ALBERTO MO…»,
  [captura](capturas/escritorio-gestionar-plantilla.jpg)), selector de convocatoria («ANTONIO
  ZURITA CARRA…») y formulario de resultado («EDUARDO BUSTAMAN…»).
- **Recomendación**: usar `short_name` (nombre + primer apellido) en chips y rejillas, permitir
  dos líneas en vez de una, y en «Gestionar plantilla» pasar a 3 columnas o lista en escritorio.
- **Esfuerzo**: S.

### H-22 · «Primeros pasos» empuja el próximo partido fuera de la pantalla

- **Categoría**: UI y jerarquía visual · **Severidad**: Media · **Prioridad**: 180 (3×4×3×5)
- **Evidencia (C1)**: con 4 de 5 pasos hechos, la lista sigue con sus 5 filas (unos 500 px); en
  móvil el «Próximo partido» empieza por debajo de los 900 px ([captura](capturas/movil-inicio-capitan.jpg)).
- **Recomendación**: plegar los pasos hechos en «4 de 5 hechos» y mostrar solo el siguiente;
  colocar el bloque «Pendiente» (H-02) y el próximo partido por encima.
- **Esfuerzo**: S.

### H-16 · Estadísticas: el mismo balance tres veces y un gráfico engañoso

- **Categoría**: Información duplicada · **Severidad**: Media · **Prioridad**: 180 (3×4×3×5)
- **Evidencia (C1)**: el balance 7-0-7 aparece como cifra grande, como «Partidos ganados 50,0 %»
  y como gráfico circular con la leyenda 50,0 % / 0,0 % / 50,0 %. «Juegos como local 418–358» se
  repite en un gráfico de barras con porcentajes. El gráfico «Partidos ganados por año» une las
  temporadas con curvas suavizadas (`tension: 0.35` en `static/js/team_statistics.js`) que dibujan
  valores entre temporadas que no existen, y la temporada en curso cae a 0 como si fuese un
  desplome.
- **Recomendación**: dejar el balance en la cabecera y quitar el circular; barras agrupadas por
  temporada (o línea recta `tension: 0`) con la temporada en curso marcada como «en curso».
- **Esfuerzo**: S.

### H-17 · Temporada por defecto distinta en cada pantalla

- **Categoría**: Errores e inconsistencias · **Severidad**: Media · **Prioridad**: 180 (3×4×3×5)
- **Evidencia**: (C1) Partidos abre en 2026-2027; Estadísticas de equipo abre en «Todas».
  (C2) `match/views.py` y `warnings_statistics` usan `current_season()` por defecto;
  `team_statistics`, `statistics_per_player` y `statistics_per_pair` usan todas.
- **Problema**: los números de Partidos (1 jugado) y Estadísticas (14 jugados) no cuadran a
  primera vista.
- **Recomendación**: misma regla en todas (temporada actual, con «Todas» a un toque) y recordar la
  última elección en la sesión.
- **Esfuerzo**: XS.

### H-18 · Formatos de puntos SNP y fechas mezclados

- **Categoría**: UI y jerarquía visual · **Severidad**: Baja · **Prioridad**: 150 (2×5×3×5)
- **Evidencia (C1)**: jugadores «SNP 50714,29», «SNP 56250,0», «SNP -»; estadísticas «68 500»;
  alineación «103281.3 pts»; fechas «27/09/2026» (partido, inicio) frente a «dom 27 Sep 2026»
  (listado).
- **Recomendación**: un filtro de plantilla para puntos (entero con separador de miles, «Sin
  SNP») y un formato de fecha corto común (`D j M Y`).
- **Esfuerzo**: S.

### H-19 · Cuatro paginaciones distintas

- **Categoría**: Errores e inconsistencias · **Severidad**: Media · **Prioridad**: 120 (2×4×3×5)
- **Evidencia (C1/C2)**: equipos 4 por página con «1 de 2 Siguiente »» (servidor); jugadores 9
  por página con flechas y «1–9 de 23» (JS en cliente); partidos 12 por página; convocatoria 20.
- **Recomendación**: un solo componente (`core/templates/includes/pagination.html`) y tamaños
  pensados para plantillas de 15-30: sin paginar hasta 30 elementos en jugadores y equipos.
- **Esfuerzo**: S.

### H-30 · A 320 px las barras fijas tapan el contenido

- **Categoría**: Responsive · **Severidad**: Media · **Prioridad**: 120 (3×2×4×5)
- **Evidencia (C1)**: en «Crear convocatoria» a 320×640, la barra «0 seleccionados · Crear
  convocatoria» y la barra de navegación ocupan cerca del 40 % del alto y tapan la primera tarjeta
  ([captura](capturas/movil-320-crear-convocatoria.jpg)); el botón desborda 1 px.
- **Recomendación**: ocultar la barra inferior de navegación mientras hay una barra de acción
  fija (o fusionarlas), y `padding-bottom` del `main` igual a su alto.
- **Esfuerzo**: S.

### H-39 · Mayúsculas, dos puntos y títulos sin criterio único

- **Categoría**: UI y jerarquía visual · **Severidad**: Baja · **Prioridad**: 20
- **Evidencia (C1)**: «Invitar jugadores» y «Configurar la cuenta» en minúsculas entre títulos en
  mayúsculas; «Crear Partido» (mayúscula en cada palabra) frente a «Nuevo partido»; etiquetas «Tipo
  de partido:», «Fecha:» con dos puntos frente a «Modo» sin ellos.
- **Recomendación**: guía de estilo de una página en `docs/mantener-documentacion.md`.
- **Esfuerzo**: XS.

### H-32 · Lema en inglés en la portada en español

- **Categoría**: UI · **Severidad**: Baja · **Prioridad**: 25 · **Evidencia (C1)**:
  «IMPROVE YOUR LEVEL» en `core/templates/landing.html`, con msgid y msgstr en inglés.
- **Recomendación**: lema en español («Sube el nivel de tu equipo») y su traducción. **Esfuerzo**: XS.

### H-34 · Selector de archivo nativo sin estilo ni idioma de la página

- **Categoría**: UI · **Severidad**: Baja · **Prioridad**: 12 · **Confianza**: C3
- **Evidencia (C1)**: en «Editar mi jugador» y «Crear jugador» se ve «Choose File / No file chosen»
  del navegador ([captura](capturas/movil-editar-mi-jugador.jpg)). El idioma depende del
  navegador: con Chromium en español saldría en español (no comprobado).
- **Recomendación**: botón propio «Subir foto» que abre el recorte existente (`static/js/photo-crop.js`).

## Accesibilidad

El análisis automático con axe-core 4.10 (reglas WCAG 2.0/2.1/2.2 A y AA y buenas prácticas)
dio **0 incumplimientos** en las 23 pantallas del capitán a 1280, 768 y 390 px, en las 11 del
miembro y en las 8 públicas. Es un buen punto de partida, pero no implica conformidad: los
hallazgos siguientes salen de pruebas manuales con teclado y de medidas en el navegador.

### H-27 · El foco de teclado queda bajo la barra inferior

- **Categoría**: Accesibilidad (WCAG 2.2 · 2.4.11 Foco no oculto, mínimo) · **Severidad**: Media ·
  **Prioridad**: 108 (3×3×3×4)
- **Evidencia (C1)**: recorriendo con Tab el partido en móvil, el foco en «Ver 1 más» queda en
  y = 816-844 px y el de «Ver partido» del listado en y = 776-796 px, bajo la barra de
  navegación fija. `static/style.css` no define `scroll-padding-bottom`. Queda tapado
  parcialmente (no incumple 2.4.11 si se ve una parte, pero sí 2.4.12 de nivel AAA).
- **Recomendación**: `html { scroll-padding-bottom: <alto de la barra + 16px>; scroll-padding-top:
  <alto de la cabecera>; }`.
- **Esfuerzo**: XS.

### H-28 · Objetivos táctiles pequeños

- **Categoría**: Accesibilidad (WCAG 2.2 · 2.5.8 Tamaño del objetivo, mínimo) · **Severidad**: Baja ·
  **Prioridad**: 72 (2×3×3×4)
- **Evidencia (C1)**: el lápiz «Cambiar fecha» mide 13×14 px; «Ver partido» 84×20 px; los enlaces
  de vuelta («← PARTIDOS») 19 px de alto. axe no los marca porque hay espacio libre alrededor
  (excepción de espaciado), pero son difíciles de acertar con el pulgar.
- **Recomendación**: área mínima de 24×24 px (ideal 44×44 en acciones frecuentes) con `padding`
  sin cambiar el tamaño visual.

### Otros puntos de accesibilidad revisados (sin hallazgo nuevo)

- Enlace «Saltar al contenido» presente y primero en el orden de foco (C1).
- Foco visible en enlaces, botones y campos: contorno o sombra lima (C1). En las tarjetas de
  partido el foco se pinta en toda la tarjeta (`.z-fixture:focus-within`) aunque el enlace tenga
  `outline: none` (C1).
- `prefers-reduced-motion` respetado en transiciones (`static/style.css`) (C2).
- Advertencias del selector solo en `title`: ver H-29 (no las lee un lector de pantalla).
- No se ha probado con lector de pantalla real ni a 200 % de zoom (ver [07](07-audit-coverage.md)).

## Seguridad e incoherencias de datos con efecto en la experiencia

### H-23 · En «Miembros» se cambia el email sin contraseña

- **Categoría**: Errores e inconsistencias (duplicidad con riesgo) · **Severidad**: Alta ·
  **Prioridad**: 64 (4×1×4×4) · **Confianza**: C2 (inspección, no ejecutado)
- **Evidencia**: la tabla de `/core/members/` tiene un campo email editable y «Guardar email» para
  la fila propia del capitán ([captura](capturas/escritorio-miembros.jpg)). `update_member`
  (`core/views.py`) llama a `_change_own_email` sin pedir contraseña, mientras que «Mi perfil» exige la
  contraseña actual (`EmailChangeForm.clean_current_password` en `core/forms.py`).
- **Problema**: dos sitios para lo mismo con reglas distintas; con una sesión abierta ajena se
  puede cambiar el email del capitán y, con él, recuperar la contraseña.
- **Recomendación**: quitar el campo de la tabla de miembros y enlazar a «Mi perfil».
- **Esfuerzo**: XS · **Validación**: test que compruebe que `update_member` ya no cambia el email.

### H-24 · «Mi perfil» enseña a los miembros una preferencia de capitán

- **Categoría**: Información duplicada · **Severidad**: Baja · **Prioridad**: 40
- **Evidencia (C1)**: el miembro ve «Datos del informe PDF al crear un partido» aunque no puede
  crear partidos ([captura](capturas/movil-perfil-miembro.jpg)).
- **Recomendación**: mostrar ese bloque solo a capitanes. **Esfuerzo**: XS.

### H-37 · «Ver estadísticas» en racha solo para el capitán

- **Severidad**: Baja · **Prioridad**: 20 · **Evidencia (C2)**: en `core/templates/home.html` el
  botón del jugador en racha lleva `{% if is_club_admin %}` y el de la pareja no; las dos páginas
  de destino son visibles para miembros (`club_required`).
- **Recomendación**: mostrar los dos a todos. **Esfuerzo**: XS.

---

## Fortalezas que conviene conservar

1. **Listado de partidos en tarjetas** con estado en palabras, marcador por equipo y lugar
   ([captura](capturas/escritorio-partidos.jpg)): se entiende de un vistazo. Es el patrón a extender
   al inicio y al resumen del partido.
2. **Alineación sugerida** con alternativa: ahorra el paso más difícil y se puede corregir. Solo
   necesita mejor presentación en móvil (H-31).
3. **Validación de resultados en vivo** (`static/js/result-form.js`) y reglas en `match/scoring.py`:
   evita actas imposibles.
4. **Errores en popup y éxitos en toast desde un único sitio** (`core/templates/base.html`): la base técnica para
   resolver H-08 ya existe.
5. **Prevención fuerte en acciones destructivas**: borrar el club exige escribir su nombre;
   quitar a un miembro y traspasar la capitanía piden confirmación; borrar un jugador conserva
   sus partidos.
6. **Accesibilidad de base sólida**: 0 incumplimientos automáticos, enlace de salto, títulos
   únicos, foco visible y movimiento reducido.
7. **Estados vacíos con acción** («No hay partidos» + «Crear partido») y página de «Sin permiso»
   que explica qué hacer.
8. **Selector de convocatoria** con búsqueda, filtros por posición, «Elegidos» y contador con
   mínimo: buen patrón para cualquier selección múltiple.
9. **Identidad visual coherente** (oscuro + lima) y sin desbordamiento horizontal a 320, 390 y 768 px
   en las 23 pantallas medidas (salvo 1 px en H-30).
