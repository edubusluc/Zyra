# 07 · Cobertura de la auditoría

Registro de lo examinado el 15/10/2026, con qué método y qué queda pendiente. **La cobertura no es
completa**: ver § 4.

## 1. Entorno y método

- **Código**: `main` en el commit `81adb7e` (tras el PR #153). La app **no se ha modificado**: este
  PR solo añade `docs/ux-audit/`.
- **Entorno**: servidor local (`DJANGO_DEBUG=True python manage.py runserver`) con SQLite, datos de
  `populate_db.py` y escudos con `move_photos_to_media`. Cuentas creadas para la prueba: `edu`
  (capitán), `jugador` (miembro enlazado a un jugador), `nuevo` (sin club) y `staff` (no usada).
- **La web pública https://zyrapadel.com/ no se pudo abrir** desde el entorno de trabajo (el proxy
  de salida devolvió 403). Todo lo observado es la versión local de `main`; el contenido de
  producción (datos reales, rendimiento de red, correo real) no se ha visto.
- **Navegador**: Chromium headless (Playwright) en inglés de sistema con `locale es-ES`; tamaños
  1280×800, 768×1024, 390×844 y 320×640 con emulación táctil en móvil.
- **Herramientas**: script de recorrido propio (capturas a página completa y del primer pantallazo,
  alto, desbordamiento, elementos interactivos, objetivos < 24 px, encabezados, errores de consola),
  axe-core 4.10.2 (WCAG 2.0/2.1/2.2 A-AA + buenas prácticas), `scripts/auditoria_accesibilidad.py`
  del repositorio, recorrido con teclado (40 Tab por página) y un flujo completo automatizado.
- **Datos modificados**: solo en la base local de prueba (2 enfrentamientos creados y cerrados,
  1 convocatoria de 3 jugadores, 1 advertencia). Ningún dato real.

## 2. Flujos ejecutados

| Flujo | Perfil | Tamaño | Resultado | Hallazgos |
|---|---|---|---|---|
| Crear partido → convocar 12 → cerrar convocatoria → alineación sugerida → 5 resultados → cerrar acta | Capitán | 390 | Completado (×2): 19 navegaciones, 58 interacciones | H-03, H-04, H-08, H-09, H-10, H-31, H-36, H-40 |
| Crear partido sin rival | Capitán | 390 | Burbuja nativa | H-12 |
| Crear convocatoria sin jugadores | Capitán | 390 | Error claro en popup | — |
| Cerrar convocatoria con 3 | Capitán | 390 | Error tardío | H-10 |
| Aplicar advertencia | Capitán | 390 | Sin mensaje | H-07, H-08 |
| Crear jugador con nombre parecido («Alberto Montaño») | Capitán | 390 | No se envió el formulario: el aviso de nombre parecido **no se ha comprobado** | — |
| Recorrido con teclado (Partidos, Resumen) | Capitán | 1280 y 390 | Orden y foco correctos; foco bajo la barra en móvil | H-27 |
| Página «Sin permiso» al crear partido | Miembro | 1280 y 390 | 403 con explicación | — |

## 3. Pantallas examinadas

Altos en píxeles. «axe» = número de reglas incumplidas sumando todos los tamaños. «Consola» =
errores de JavaScript (se excluyen los 403/404 esperados y las fotos que faltaban antes de copiarlas
a `media/`).

#### Capitán (`edu`)

| Pantalla | URL | Estado HTTP | Alto Escritorio | Alto Tablet | Alto Móvil 390 | Interactivos | Campos | axe | Consola |
|---|---|---|---|---|---|---|---|---|---|
| home | `/` | 200 | 1420 | 1537 | 1894 | 19 | 0 | 0 | 0 |
| partidos | `/match/list_match` | 200 | 800 | 1024 | 1111 | 27 | 1 | 0 | 0 |
| crear-partido | `/match/create_match` | 200 | 1105 | 1130 | 1111 | 27 | 7 | 0 | 0 |
| partido-pendiente | `/match/call_for_match/MATDqAmU6bngCxQ/` | 200 | 860 | 1024 | 1096 | 18 | 0 | 0 | 0 |
| partido-cerrado | `/match/call_for_match/MAT2kxbkMFkELQR/` | 200 | 1809 | 2015 | 2476 | 20 | 0 | 0 | 0 |
| crear-convocatoria | `/match/create_call/MATDqAmU6bngCxQ/` | 200 | 907 | 1144 | 2239 | 46 | 21 | 0 | 0 |
| registro-conv | `/callLog/view_call_log/CALhe7ae3wfySJC` | 200 | 1200 | 1703 | 2659 | 45 | 21 | 0 | 0 |
| jugadores | `/players/list_players` | 200 | 881 | 1277 | 2067 | 42 | 2 | 0 | 0 |
| crear-jugador | `/players/create_player` | 200 | 988 | 1024 | 1032 | 24 | 6 | 0 | 0 |
| plantilla | `/players/roster/` | 200 | 1193 | 1556 | 3134 | 55 | 34 | 0 | 0 |
| jugador-detalle | `/players/player_details/PLYCPxbD4jQSWOy/` | 200 | 949 | 1024 | 1299 | 17 | 0 | 0 | 0 |
| editar-jugador | `/players/edit_player/PLYCPxbD4jQSWOy` | 200 | 1003 | 1028 | 1111 | 26 | 7 | 0 | 0 |
| snp | `/players/snp/` | 200 | 800 | 1024 | 920 | 18 | 2 | 0 | 0 |
| equipos | `/team/list_teams` | 200 | 800 | 1024 | 1241 | 26 | 2 | 0 | 0 |
| crear-equipo | `/team/create_team` | 200 | 1029 | 1054 | 1070 | 25 | 7 | 0 | 0 |
| gestionar-equipos | `/team/manage_teams/` | 200 | 1697 | 2466 | 3514 | 133 | 72 | 0 | 0 |
| editar-equipo | `/team/edit_team/TEA6axYQrV0IjL6/` | 200 | 1048 | 1073 | 1068 | 25 | 7 | 0 | 0 |
| est-equipo | `/data_analyse/team_statistics` | 200 | 5100 | 6981 | 8920 | 33 | 0 | 0 | 0 |
| est-jugador | `/data_analyse/player_statistics` | 200 | 1047 | 1560 | 2329 | 46 | 1 | 0 | 0 |
| est-pareja | `/data_analyse/pair_statistics` | 200 | 1001 | 1160 | 1696 | 36 | 2 | 0 | 0 |
| est-advertencias | `/data_analyse/warnings` | 200 | 800 | 1024 | 844 | 20 | 0 | 0 | 0 |
| perfil | `/core/profile/` | 200 | 1688 | 1665 | 1858 | 24 | 5 | 0 | 0 |
| miembros | `/core/members/` | 200 | 1038 | 1143 | 1514 | 21 | 2 | 0 | 0 |

#### Miembro (`jugador`)

| Pantalla | URL | Estado HTTP | Alto Escritorio | Alto Móvil 390 | Interactivos | Campos | axe | Consola |
|---|---|---|---|---|---|---|---|---|
| home | `/` | 200 | 979 | 1408 | 18 | 0 | 0 | 0 |
| partidos | `/match/list_match` | 200 | 963 | 1476 | 27 | 1 | 0 | 0 |
| partido-cerrado | `/match/call_for_match/MAT2kxbkMFkELQR/` | 200 | 1755 | 2382 | 17 | 0 | 0 | 0 |
| jugadores | `/players/list_players` | 200 | 881 | 1921 | 30 | 1 | 0 | 0 |
| jugador-detalle | `/players/player_details/PLYCPxbD4jQSWOy/` | 200 | 941 | 1291 | 16 | 0 | 0 | 0 |
| equipos | `/team/list_teams` | 200 | 800 | 1041 | 19 | 1 | 0 | 0 |
| est-equipo | `/data_analyse/team_statistics` | 200 | 5289 | 9073 | 32 | 0 | 0 | 0 |
| est-jugador | `/data_analyse/player_statistics` | 200 | 1047 | 2329 | 45 | 1 | 0 | 0 |
| perfil | `/core/profile/` | 200 | 1654 | 1843 | 25 | 5 | 0 | 0 |
| mi-jugador | `/players/me/` | 200 | 800 | 1018 | 21 | 3 | 0 | 0 |
| crear-partido-403 | `/match/create_match` | 403 | 826 | 918 | 15 | 0 | 0 | 0 |

#### Sin sesión

| Pantalla | URL | Estado HTTP | Alto Escritorio | Alto Móvil 390 | Interactivos | Campos | axe | Consola |
|---|---|---|---|---|---|---|---|---|
| landing | `/` | 200 | 2291 | 3664 | 16 | 0 | 0 | 0 |
| login | `/core/login/` | 200 | 826 | 918 | 16 | 2 | 0 | 0 |
| registro-elegir | `/core/register/` | 200 | 827 | 1076 | 13 | 0 | 0 | 0 |
| registro-club | `/core/register_club/` | 200 | 2331 | 2564 | 31 | 13 | 0 | 0 |
| registro-cuenta | `/core/register_account/` | 200 | 1294 | 1318 | 19 | 4 | 0 | 0 |
| guias | `/guia/` | 200 | 937 | 1286 | 13 | 0 | 0 | 0 |
| reset | `/accounts/password/reset/` | 200 | 826 | 918 | 13 | 1 | 0 | 0 |
| 404 | `/no-existe/` | 404 | 800 | 2121 | 0 | 0 | 0 | 0 |

#### Cuenta sin club (`nuevo`)

| Pantalla | URL | Estado HTTP | Alto Escritorio | Alto Móvil 390 | Interactivos | Campos | axe | Consola |
|---|---|---|---|---|---|---|---|---|
| sin-club | `/core/no_club/` | 200 | 826 | 918 | 10 | 0 | 0 | 0 |
| no-club | `/core/no_club/` | 200 | 826 | 918 | 10 | 0 | 0 | 0 |
| perfil | `/core/profile/` | 200 | 1445 | 1586 | 18 | 5 | 0 | 0 |

#### Capitán a 320 px

| Pantalla | URL | Estado HTTP | Alto Móvil 320 | Interactivos | Campos | axe | Consola |
|---|---|---|---|---|---|---|---|
| partidos | `/match/list_match` | 200 | 1582 | 29 | 1 | 0 | 0 |
| partido-cerrado | `/match/call_for_match/MAT2kxbkMFkELQR/` | 200 | 3025 | 20 | 0 | 0 | 0 |
| est-equipo | `/data_analyse/team_statistics` | 200 | 10307 | 33 | 0 | 0 | 0 |
| crear-convocatoria | `/match/create_call/MATDqAmU6bngCxQ/` | 200 | 2357 | 46 | 21 | 0 | 0 |
| gestionar-equipos | `/team/manage_teams/` | 200 | 3719 | 133 | 72 | 0 | 0 |
| miembros | `/core/members/` | 200 | 1685 | 21 | 2 | 0 | 0 |

### Hallazgos por pantalla

| Pantalla | Hallazgos |
|---|---|
| Inicio (capitán) | H-02, H-22, H-36, H-37 |
| Inicio (miembro) | H-06, H-36 |
| Partidos (listado) | H-17, H-19, A2 |
| Crear partido | H-11, H-12 |
| Resumen del partido | H-01, H-03, H-09, H-10, H-20, H-21, H-28, H-40 |
| Crear/editar convocatoria | H-20, H-29, H-30 |
| Alineación | H-31 |
| Resultado | H-04, H-20 |
| Cambios en la convocatoria / sanciones | H-07, H-35 |
| Jugadores, ficha, plantilla | H-18, H-19, H-20, H-25 |
| Equipos, gestionar equipos | H-19, H-38 |
| Estadísticas (equipo, jugador, parejas, advertencias) | H-01, H-15, H-16, H-17, H-26 |
| Miembros | H-14, H-23, H-39 |
| Mi perfil, editar mi jugador | H-24, H-34 |
| Portada, registro | H-32, H-33 |
| Cabecera y barra inferior | H-13, H-14, H-27 |

## 4. Pendiente y por qué

| Área | Motivo | Riesgo de dejarlo |
|---|---|---|
| Web en producción (zyrapadel.com) | Inaccesible desde el entorno (proxy 403) | Medio: diferencias de datos, rendimiento real |
| Back-office (staff) | Fuera del foco de usuarios finales; no se recorrió con la cuenta `staff` | Bajo para usuarios, medio para el dueño |
| «Completar equipo» e importación SNP | Requiere credenciales reales de SNP | Medio: es parte del alta |
| Aceptar una invitación (email y enlace), registro como jugador | No ejecutado; solo pantallas | Medio |
| Login con Google, recuperar contraseña por correo | Requiere servicios externos | Bajo |
| Editar convocatoria, editar parejas, cambiar fecha, reabrir acta, borrar partido | Pantallas no recorridas; revisadas en plantilla | Bajo |
| Informe PDF, correos y informe mensual | Contenido no revisado en esta auditoría (hay informes previos en la carpeta del proyecto) | Bajo |
| Gestionar equipos y plantilla: aplicar cambios en lote | Solo vista, sin guardar | Bajo |
| Interfaz en inglés | No recorrida | Medio (textos guardados en BD sin traducir ya conocidos) |
| Lector de pantalla, zoom 200 %, texto grande del sistema | Sin dispositivo ni lector en el entorno | Medio |
| Rendimiento percibido en red móvil real | Servidor local sin latencia | Medio |
| Abandonar o eliminar club, traspasar capitanía, eliminar cuenta | Acciones destructivas: solo revisión de plantillas y confirmaciones | Bajo |
| Pruebas con usuarios | No realizadas: plan en [05](05-usability-testing-plan.md) | Alto: H-05, H-06, H-26, H-33 dependen de ello |

## 5. Control de calidad del estudio

1. Hallazgos sin duplicar: H-38 (equipo propio) y H-14 (menú) se separan porque se resuelven con
   cambios distintos; H-35 (registro) y H-07 (sanciones) también.
2. Rutas de archivo citadas comprobadas en el repositorio el 15/10/2026.
3. Cada recomendación del roadmap remite a un hallazgo.
4. Severidad y prioridad justificadas en cada hallazgo; H-07 y H-23 se priorizan por riesgo.
5. Hechos (C1/C2) separados de hipótesis (C3) y oportunidades (C4).
6. Pantallas pendientes listadas en § 4.
7. Decisiones de producto marcadas: término del nivel superior (H-01), disponibilidad (H-05),
   visibilidad de «Peores parejas» (H-26), nueva navegación (S1).
8. No se ha modificado la aplicación: el PR solo contiene `docs/ux-audit/`.
