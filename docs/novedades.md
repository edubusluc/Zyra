# Novedades

Registro de lo que entra en `main`, de lo más reciente a lo más antiguo. Cada pull request que
añade o cambia una funcionalidad suma aquí una línea (ver [Mantener la documentación](mantener-documentacion.md)).

## 17/10/2026 · Back-office: jugador enlazado en la ficha de usuario

- La tarjeta «Cuenta» de la ficha de usuario muestra el jugador (y equipo/club) al que está enlazada la cuenta, o «Sin enlazar»

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
