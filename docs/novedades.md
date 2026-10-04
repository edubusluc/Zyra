# Novedades

Registro de lo que entra en `main`, de lo más reciente a lo más antiguo. Cada pull request que
añade o cambia una funcionalidad suma aquí una línea (ver [Mantener la documentación](mantener-documentacion.md)).

## 04/10/2026

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
