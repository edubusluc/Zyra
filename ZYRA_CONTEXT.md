# ZYRA_CONTEXT · índice técnico

Punto de entrada para retomar cualquier tarea sin explorar todo el repositorio. Dirige la
investigación; no sustituye leer el código. Verificado contra `main` el 09/10/2026 (tras #105).
Leyenda: **[V]** comprobado en código o tests · **[I]** inferido · **[?]** pendiente de verificar.

## Cómo usarlo (3 pasos, ~1.000 tokens)

1. **Busca, no leas entero:** `grep -n -i "<palabra>" ZYRA_CONTEXT.md`. Cada fila de la tabla tiene una
   columna *Claves* con sinónimos en español e inglés (p. ej. `portada`, `landing`, `alineación`, `lineup`):
   una sola línea devuelve vistas, lógica, plantillas, JS, datos y tests del área.
2. **Mira la receta** del tipo de cambio en [Recetas](#recetas-qué-tocar-según-el-cambio): lista lo que hay que
   tocar siempre (traducciones, tests, novedades…), para no descubrirlo a mitad de tarea.
3. **Abre `docs/ai/` solo si tocas reglas, modelos o flujos** (enlace en la última columna). Para un cambio
   visual o de texto basta con la fila y la receta.

Si la palabra no aparece, prueba un sinónimo o el nombre de la plantilla; si el área no está, añádela en el
mismo PR.

## Qué es y con qué está hecho [V]

Web multi-club para capitanes de equipos de pádel de las Series Nacionales de Pádel (SNP, snpgalaxy.com):
plantilla, rivales, enfrentamientos, convocatorias, alineaciones, resultados, informe PDF por email,
estadísticas y back-office del dueño de la plataforma. Español con traducción al inglés.

- Python 3.11 · Django 5.1 · django-allauth (usuario/email + Google) · `requirements.txt`.
- SQLite en local, PostgreSQL 16 en producción (`DATABASE_URL`). Hosting sin decidir; Netlify solo previews (`netlify.toml`).
- ReportLab (PDF), Pillow (fotos → WebP), Playwright (scraper SNP), cryptography (Fernet), boto3 (Rekognition / S3), sentry-sdk.
- Front sin framework ni build: plantillas Django + `static/style.css` + `static/js/*.js`.
- Sin colas: tareas en hilos y un lanzador `run_scheduler` llamado por cron.
- Docs: MkDocs Material + mkdocstrings (`mkdocs.yml`, `requirements-docs.txt`).

## Arquitectura en una línea por pieza

- Configuración: `zyra/settings.py` (todo por entorno), URLs `zyra/urls.py`.
- Cada petición: `core/middleware.py` (`CurrentClubMiddleware`) pone `request.club` / `request.membership`;
  las vistas usan `core/decorators.py` (`club_required`, `club_admin_required` = capitán).
- `core/context_processors.py` da a todas las plantillas `club`, `navigation`, `google_login`, `site`.
- Apps: `core`, `players`, `team`, `match`, `call`, `callLog`, `penalty`, `data_analyse`, `backoffice`.
  Las plantillas viven en `<app>/templates/` (sin subcarpeta, salvo `backoffice/templates/backoffice/`).
- Detalle de capas y flujos: [docs/ai/architecture.md](docs/ai/architecture.md).

## Índice por funcionalidad

| Área | Claves | Vistas y URLs | Lógica | Plantillas y JS | Datos | Tests | Doc |
|---|---|---|---|---|---|---|---|
| Portada, inicio, base y navegación | portada, landing, home, inicio, cabecera, menú, navbar, pie, footer, volver arriba, primeros pasos, onboarding, transiciones, 404, 403 | `core/views.py` (`home`, `no_club`, `error_404_view`, `error_403_view`) | `core/seo.py` (FAQ y JSON-LD de la portada), `core/onboarding.py`, `core/context_processors.py` | `core/templates/landing.html` (pública), `core/templates/home.html` (club), `core/templates/base.html`, `core/templates/includes/messages_popup.html`, `core/templates/404.html`, `static/js/nav.js`, `static/js/page-transitions.js`, `static/js/a11y.js` | — | `core/tests.py`, `core/tests_onboarding.py`, `core/tests_seo.py`, `core/tests_accessibility.py` | [architecture](docs/ai/architecture.md) |
| Estilos y diseño | css, estilos, colores, tema, móvil, responsive, tarjetas, botones, modal, popup, toast | — | secciones de `static/style.css` (ver receta «Cambio visual») | `static/style.css`, `core/templates/includes/form_fields.html`, `core/templates/includes/pagination.html` | — | `core/tests_accessibility.py` | `docs/mantener-documentacion.md` § Accesibilidad |
| Acceso, registro, Google, contraseñas | login, registro, signup, google, contraseña, password, recuperar, cuenta | `core/urls.py`, `core/views.py` (`register_club`, `ThrottledLoginView`) | `core/forms.py`, `core/adapters.py`, `core/services.py` (`create_club`) | `core/templates/register_club.html`, `core/templates/registration/login.html`, `core/templates/account/`, `core/templates/includes/google_button.html`, `core/templates/includes/password_rules.html`, `static/js/password.js` | `User`, `Club`, `Membership`, `Player.user` | `core/tests.py`, `core/tests_password.py`, `core/tests_security.py`, `players/test_own_player.py` | [business-rules § Cuentas](docs/ai/business-rules.md#cuentas-y-clubes) |
| «Mi perfil» | mi perfil, profile, email, cambiar correo, mi jugador, enlazar jugador, quién eres | `core/views.py` (`my_profile`), `players/views.py` (`my_player`) | `core/forms.py`, `players/forms.py` | `core/templates/my_profile.html`, `players/templates/link_player.html`, `players/templates/my_player.html`, `static/js/link-player.js` | `User`, `Player.user` | `core/tests_profile.py`, `players/test_own_player.py` | [business-rules § Cuentas](docs/ai/business-rules.md#cuentas-y-clubes) |
| Club, miembros, invitaciones, capitanes | club, miembros, members, invitación, invite, enlace, capitán, captain, abandonar, leave, eliminar club | `core/views.py` (`club_members`, `create_invitation*`, `invitation`, `leave_club`) | `core/services.py` (`accept_invitation`, `remove_membership`, `delete_club`), `core/emails.py` | `core/templates/club_members.html`, `core/templates/invitation.html`, `core/templates/invitation_invalid.html`, `core/templates/emails/`, `static/js/leave-club.js` | `Club`, `Membership`, `Invitation` | `core/tests_invitations.py`, `core/tests_delete_club.py` | [business-rules § Cuentas](docs/ai/business-rules.md#cuentas-y-clubes) |
| Jugadores y plantilla | jugador, player, plantilla, roster, foto, nombre parecido, similar, borrar jugador | `players/urls.py`, `players/views.py` (`list_players`, `create_player`, `edit_player`, `show_player`, `manage_roster`, `delete_player`) | `players/forms.py`, `core/similarity.py`, `core/images.py` | `players/templates/list_players.html`, `players/templates/create_player.html`, `players/templates/edit_player.html`, `players/templates/player_detail.html`, `players/templates/manage_roster.html`, `players/templates/confirm_delete.html`, `core/templates/includes/similar_modal.html`, `static/js/similar-check.js`, `static/js/photo-crop.js` | `Player` | `players/tests.py`, `core/test_images.py` | [data-model § Player](docs/ai/data-model.md#player) |
| SNP: puntos y «Completar equipo» | snp, puntos, ranking, scraper, completar equipo, importar, categoría | `players/views.py` (`snp_account`, `complete_team_*`), comandos `update_snp_scores`, `complete_snp_team` | `players/scraper.py`, `players/snp.py`, `players/snp_import.py`, `core/crypto.py` | `players/templates/snp_account.html`, `players/templates/complete_team_welcome.html`, `players/templates/includes/snp_category.html` | `SnpAccount`, `SnpScoreHistory`, `SnpTeamImport` | `players/tests.py` | [business-rules § SNP](docs/ai/business-rules.md#snp) |
| Equipos (propio y rivales) | equipo, team, rival, división, grupo, gestionar equipos | `team/urls.py`, `team/views.py` (`list_team`, `create_team`, `edit_team`, `manage_teams`) | `team/forms.py` (`Teamform.clean`), `core/similarity.py` | `team/templates/list_teams.html`, `team/templates/create_team.html`, `team/templates/edit_team.html`, `team/templates/manage_teams.html` | `Team` | `team/tests.py` | [business-rules § Equipos](docs/ai/business-rules.md#equipos) |
| Partidos (enfrentamientos, amistosos) | partido, match, enfrentamiento, amistoso, friendly, listado, tarjetas, buscador, calendario, fecha | `match/urls.py`, `match/views.py` (`list_match`, `create_match`, `call_for_match`, `delete_match`) | `match/forms.py` (`MatchForm`) | `match/templates/list_match.html`, `match/templates/create_match.html`, `match/templates/call_for_match.html` (detalle), `match/templates/delete_match.html`, `match/templates/includes/match_team_card.html`, `static/js/match-form.js`, `static/js/date-picker.js`, `static/js/player-picker.js` | `Match` | `match/tests.py`, `match/tests_flow.py` | [business-rules § Partidos](docs/ai/business-rules.md#partidos-convocatorias-y-actas) |
| Convocatorias, registro y advertencias | convocatoria, call, convocados, cerrar convocatoria, registro, log, advertencia, penalty, warning | `match/views.py` (`create_call`, `edit_call`, `close_call`, `existing_call_view`, `closed_call`), `call/views.py`, `callLog/views.py`, `penalty/views.py` | idem (sin capa de servicio) | `match/templates/create_call.html`, `match/templates/edit_call.html`, `match/templates/includes/player_selector.html`, `call/templates/existing_call.html`, `call/templates/closed_call.html`, `callLog/templates/view_call_log.html`, `static/js/player-selector.js` | `Call`, `CallLog`, `Penalty` | `match/tests.py`, `call/tests.py`, `callLog/tests.py`, `penalty/tests.py` | [business-rules § Partidos](docs/ai/business-rules.md#partidos-convocatorias-y-actas) |
| Alineación, resultados y cierre de acta | alineación, lineup, parejas, pairs, resultado, result, sets, acta, cerrar partido, alineación sugerida | `match/views.py` (`create_game_for_match`, `edit_game_match`, `create_result`, `edit_result`, `close_match`, `suggested_lineup`) | `match/lineup.py`, `match/scoring.py`, `match/advisor.py` | `match/templates/create_game.html`, `match/templates/edit_game_match.html`, `match/templates/create_result.html`, `match/templates/edit_result.html`, `match/templates/includes/lineup_form.html`, `match/templates/includes/result_form.html`, `static/js/lineup.js`, `static/js/result-form.js` | `Game`, `Result` | `match/tests.py`, `match/tests_flow.py`, `match/tests_suggest.py` | [business-rules § Partidos](docs/ai/business-rules.md#partidos-convocatorias-y-actas) |
| Informe PDF y correo | informe, pdf, report, correo, email, reenviar | `match/views.py` (`close_call`, `call_report_pdf`, `resend_call_report`), comando `send_call_reports` | `match/report.py`, `match/report_pdf.py`, `match/notifications.py`, `core/emails.py` | `core/templates/emails/layout.html` | `ReportDelivery` | `match/tests_report.py` | [business-rules § Informe](docs/ai/business-rules.md#informe-pdf-y-correos) |
| Estadísticas | estadísticas, stats, gráficos, charts, balance, afinidad, racha, récords, temporada | `data_analyse/urls.py`, `data_analyse/views.py` (`team_statistics`, `statistics_per_player`, `statistics_per_pair`, `warnings_statistics`) | `data_analyse/pairs.py`, `data_analyse/sets.py`, `data_analyse/records.py` | `data_analyse/templates/team_statistics.html`, `data_analyse/templates/player_statistics.html`, `data_analyse/templates/pair_statistics.html`, `data_analyse/templates/warnings_statistics.html`, `data_analyse/templates/includes/`, `static/js/team_statistics.js`, `static/js/player_statistics.js`, `static/js/pair_statistics.js` | lee `Match`/`Game`/`Result`/`Call`/`Penalty` | `data_analyse/tests.py`, `data_analyse/tests_extra.py` | [business-rules § Estadísticas](docs/ai/business-rules.md#estadísticas) |
| Back-office (staff) | backoffice, staff, admin, crm, métricas, uso, salud, sql, importar | `backoffice/urls.py`, `backoffice/views.py` | `backoffice/metrics.py`, `backoffice/sql.py`, `backoffice/importer.py`, `backoffice/middleware.py`, `backoffice/decorators.py` | `backoffice/templates/backoffice/`, `static/js/backoffice-sql.js` | `UserActivity`, `RequestMetric`, `SavedQuery`, `QueryLog`, `ImportJob` | `backoffice/tests.py` | `Readme.md` § Back-office |
| Procesos programados | cron, scheduler, proceso, job, tarea programada | `backoffice/jobs.py` (`JOBS`), comando `run_scheduler` | `backoffice/scheduler.py`, `backoffice/cron.py` | `backoffice/templates/backoffice/job_list.html` | `ScheduledJob`, `JobRun` | `backoffice/tests.py` | [workflows § Procesos](docs/ai/workflows.md#procesos-programados) |
| Fotos y moderación | foto, photo, moderación, rekognition, bloqueo, suspender | formularios con `clean_photo`, `backoffice/views.py` (`photo_*`) | `core/images.py`, `core/moderation.py`, `core/blocklist.py` | `backoffice/templates/backoffice/photo_list.html`, `static/js/photo-crop.js` | `PhotoCheck`, `PhotoRemoval`, `BlockedEmail` | `core/test_images.py`, `core/tests_blocklist.py` | [business-rules § Fotos](docs/ai/business-rules.md#fotos-moderación-y-bloqueos) |
| Idioma, SEO, legal, accesibilidad | idioma, inglés, traducción, i18n, seo, sitemap, robots, hreflang, legal, privacidad, cookies, accesibilidad, a11y, aria | `core/middleware.py` (`LanguageMiddleware`, `CanonicalHostMiddleware`), `core/views.py` (`legal_page`, `robots_txt`) | `core/seo.py`, `core/sitemaps.py`, `locale/en/LC_MESSAGES/` | `core/templates/legal/`, `core/templates/robots.txt`, `static/js/a11y.js` | — | `core/tests_i18n.py`, `core/tests_seo.py`, `core/tests_accessibility.py` | `docs/mantener-documentacion.md` § Accesibilidad |
| Identificadores públicos | public_id, pid, url, identificador | `core/public_id.py` (`PublicIdModel`, conversor `<pid:...>`) | — | — | todos los modelos de dominio | `core/tests_public_id.py` | [decisions](docs/ai/decisions.md) |
| Datos de partida / reset | reset, populate, datos de prueba, borrar base de datos | `clear_database.py`, `populate_db.py` | — | — | todas | no identificados | [workflows](docs/ai/workflows.md#base-de-datos) |

## Recetas: qué tocar según el cambio

| Cambio | Toca siempre | Comprueba con |
|---|---|---|
| Texto visible nuevo o cambiado | `{% translate %}` / `gettext` + `locale/en/LC_MESSAGES/django.po` (y `locale/en/LC_MESSAGES/djangojs.po` si es JS) + `compilemessages` | `DJANGO_DEBUG=True python manage.py test core.tests_i18n` |
| Cambio visual | Busca la sección con `grep -n "^/\* ---" static/style.css` (Portada, Listados, Tarjetas, Formularios, «Móvil: revisión general»…); el bloque `st-` es de estadísticas | tests del área + `core.tests_accessibility` |
| Pantalla nueva | URL en `<app>/urls.py`, vista con `club_required`, plantilla con `{% block page_title %}`, URL en `core/tests_accessibility.py`, fila en esta tabla | tests del área |
| Campo o modelo nuevo | `makemigrations` en el mismo PR; si se expone en URL, `PublicIdModel`; filtrar por `request.club`; `docs/ai/data-model.md` | `makemigrations --check --dry-run` |
| Regla de negocio | Lógica en el módulo de la fila (no en la plantilla); `docs/ai/business-rules.md` | tests del área |
| Comando o proceso | `<app>/management/commands/`, `JobSpec` en `backoffice/jobs.py` si es periódico; `docs/ai/workflows.md` | `backoffice.tests` |
| JS nuevo | `static/js/<nombre>.js` incluido desde la plantilla; textos con `gettext` de `djangojs`; añádelo a la fila del área | `python scripts/check_ai_docs.py` |
| Cualquier PR | docstrings en español, `docs/funcionalidades.md` si cambia lo visible, línea en `docs/novedades.md` con el número del PR | `python scripts/check_docstrings.py` |

## Reglas críticas (no romper) [V]

1. Todo dato de dominio se filtra por `request.club`; nunca se busca un objeto solo por id
   (helpers `club_match`, `club_call` en `match/views.py`).
2. URLs con `public_id` (`<pid:...>`), nunca el `pk`. Modelo nuevo expuesto → `PublicIdModel` con prefijo propio.
3. Una cuenta pertenece a un solo club (`core.services.club_of`). Siempre queda al menos un capitán.
4. Convocatoria cerrable con ≥10 jugadores; partidos solo con convocatoria cerrada; acta con 5 partidos con resultado.
5. Acta cerrada (`Match.draft_mode=False`) = inmutable: no se borra el partido ni su convocatoria ni se editan parejas.
6. Resultados validados por `match/scoring.py`; `Game.save()` y `Result.save()` llaman a `clean()`.
7. Borrar un jugador conserva partidos (`SET_NULL` + `Game.removed_player_names`).
8. Cambio de modelo → migración en el mismo PR (CI: `makemigrations --check`).
9. Toda función/clase/módulo nuevo lleva docstring en español (CI: `scripts/check_docstrings.py`).
10. Textos visibles en español con `gettext`/`{% translate %}` + traducción en `locale/en/`.
11. Nunca secretos en código: todo por variables de entorno (`.env.example` las documenta).
12. Errores en popup y éxitos en toast, solo desde `core/templates/base.html`; no pintes mensajes en cada plantilla.

## Comandos esenciales [V]

```bash
DJANGO_DEBUG=True python manage.py runserver
DJANGO_DEBUG=True python manage.py test match.tests_flow        # solo el área tocada (la suite entera tarda ~11 min)
DJANGO_DEBUG=True python manage.py makemigrations --check --dry-run
python scripts/check_docstrings.py && python scripts/check_ai_docs.py && mkdocs build --strict
```

Resto (migraciones de datos, scheduler, i18n, reset, despliegue): [docs/ai/workflows.md](docs/ai/workflows.md).

## Problemas conocidos vigentes

- [V] El freno de login (`core/views.py`, `ThrottledLoginView._key`) usa `REMOTE_ADDR`; detrás de un
  proxy todas las peticiones comparten IP. [I] Con la caché por defecto el contador es por proceso.
- [V] Textos sin traducir guardados en BD: motivo de `Penalty` (`penalty/views.py`) y líneas de
  `CallLog` (`match/views.py`, `edit_call`).
- [V] Nombres `related_name` engañosos (`Call.match` → `match.match`, etc.): ver [data-model](docs/ai/data-model.md#trampas-de-related_name).
- [V] `call/templates/closed_call.html` y `call/templates/existing_call.html` están en `call/` pero los pinta `match/views.py`.
- [V] Partes de `Readme.md` § Multi-club están desfasadas (rol «Administrador», enlace de un solo uso,
  varios clubes por usuario). Manda el código; ver [decisions](docs/ai/decisions.md).

## Mantener este índice

- Va en el mismo PR que el cambio, junto con lo que pide `docs/mantener-documentacion.md`.
- App, plantilla principal, JS o test nuevo → a su fila (con claves si el área es nueva). Regla →
  `docs/ai/business-rules.md`. Modelo → `docs/ai/data-model.md`. Comando → `docs/ai/workflows.md`.
  Cambio de enfoque → `docs/ai/decisions.md`.
- Rutas siempre completas desde la raíz y entre comillas invertidas. Marca [I]/[?] lo no comprobado.
- `python scripts/check_ai_docs.py` (en CI) falla si una ruta citada no existe o si un archivo de
  `static/js/`, un test o un comando de gestión no aparece en el índice o en `docs/ai/`.
