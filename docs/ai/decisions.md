# Decisiones de arquitectura (para asistentes)

Decisiones vigentes que condicionan cambios futuros. Cuando el motivo no está escrito en el código
o en la documentación del repositorio se indica «Motivo: no documentado». Historial completo de
cambios: `docs/novedades.md`. Índice general: `ZYRA_CONTEXT.md`. Verificado el 09/10/2026.

## D1. Multi-club por filtrado en la aplicación

- **Decisión**: un único esquema; cada fila de dominio cuelga de `Club` y las vistas filtran por
  `request.club` (`core/middleware.py`, `core/decorators.py`).
- **Motivo**: varios clubes en la misma instalación sin ver datos ajenos (`Readme.md` § Multi-club, docstring de `core.models.Club`).
- **Consecuencias**: toda consulta nueva debe filtrar por club; no hay protección a nivel de BD.
  `Team.club`, `Player.club` y `Match.club` son `null=True` solo por la migración de datos antiguos (comentario en `team/models.py`).

## D2. Una cuenta, un club

- **Decisión**: un usuario solo puede pertenecer a un club no suspendido (`core.services.club_of`).
- **Motivo**: no documentado. El modelo `Membership` y el selector `switch_club` siguen admitiendo varios.
- **Consecuencias**: comprobarlo en cualquier nueva vía de alta; cuentas antiguas pueden tener más de una membresía.

## D3. Identificadores públicos en las URLs

- **Decisión**: `PublicIdModel` (prefijo de 3 letras + 12 aleatorios) y conversor `<pid:...>`; el `pk` sigue en los FK.
- **Motivo**: que no se vean números consecutivos en las URLs (`Readme.md` § Identificadores públicos).
- **Consecuencias**: modelo nuevo visible en URLs → heredar `PublicIdModel` con prefijo único; plantillas y
  redirects usan `obj.public_id`. Las páginas de usuarios del back-office siguen con el id de Django.

## D4. Migraciones en git y verificadas en CI

- **Decisión**: migraciones versionadas; CI ejecuta `makemigrations --check`.
- **Motivo**: antes cada entorno generaba las suyas (`Readme.md` § Base de datos); el motivo exacto del cambio no está escrito.
- **Consecuencias**: cada cambio de modelo incluye su migración; las migraciones de datos pueden vivir en `migrations/`.

## D5. Configuración segura por defecto

- **Decisión**: todo por entorno; sin `DJANGO_DEBUG=True` se arranca como producción y faltar
  `DJANGO_SECRET_KEY` o `FIELD_ENCRYPTION_KEY` impide arrancar (`zyra/settings.py`).
- **Motivo**: no publicar secretos ni arrancar en producción con claves inseguras (`.env.example`, `netlify.toml`).
- **Consecuencias**: tests y comandos locales necesitan `DJANGO_DEBUG=True`.

## D6. Conservar el historial deportivo

- **Decisión**: borrar un jugador no borra partidos (`Game` FK `SET_NULL` + `removed_player_names`);
  `in_team=False` en vez de borrar; acta cerrada inmutable; `Match.location` es copia, no enlace.
- **Motivo**: que estadísticas y partidos pasados no cambien (comentarios en `match/models.py`, `call/views.py` y `Readme.md` § Portada).
- **Consecuencias**: no introducir `CASCADE` desde `Player` hacia `Game`; no recalcular datos de partidos cerrados.

## D7. Solo se guardan los jugadores propios en cada `Game`

- **Decisión**: el lado rival de un `Game` queda vacío; amistosos contra rival escrito a mano usan
  `Match.rival_name` sin crear `Team`.
- **Motivo**: Zyra gestiona un solo equipo por club; el amistoso con rival libre evita llenar la lista de equipos (docstrings de `match/models.py`; el segundo, inferido de `Match.rival_name`).
- **Consecuencias**: usar `local_name`/`visiting_name`/`rival_label` y no suponer que `local` y `visiting` existen.

## D8. Sin cola de tareas: hilos + lanzador por cron

- **Decisión**: `run_scheduler` cada minuto ejecuta `backoffice/jobs.py`; trabajo puntual en `threading.Thread`.
  El envío de informes es una cola en BD (`ReportDelivery`) con reintentos.
- **Motivo**: no documentado. [I] Mantener el despliegue simple, sin Redis/Celery.
- **Consecuencias**: el servidor debe programar `run_scheduler`; los hilos mueren con el proceso; un
  proceso no se lanza dos veces mientras dé latido (`backoffice/scheduler.py`).

## D9. SNP por scraping con límites

- **Decisión**: Playwright contra snpgalaxy.com con lotes, pausas aleatorias y freno ante 403/429/503;
  credenciales cifradas con Fernet.
- **Motivo**: evitar que SNP bloquee a Zyra o la cuenta del capitán (`Readme.md` § Puntos SNP). Que no haya API oficial: no documentado.
- **Consecuencias**: cambios en el HTML de SNP rompen `players/scraper.py`; no reintentar fallos de credenciales.

## D10. Idioma: español fuente, inglés opcional

- **Decisión**: msgid en español; inglés en `locale/en/`; no se usa el idioma del navegador (`core.middleware.LanguageMiddleware`).
- **Motivo**: la web sale en español hasta que alguien elige otro idioma (docstring del middleware).
- **Consecuencias**: todo texto nuevo con `gettext`/`{% translate %}` y su traducción.

## D11. Back-office propio; Django admin solo de emergencia

- **Decisión**: panel en `/backoffice/` para staff; admin de Django solo superusuarios en `ADMIN_URL`.
- **Motivo**: panel del dueño de la plataforma (`Readme.md` § Back-office); el admin se oculta cambiando la ruta.
- **Consecuencias**: funciones de gestión nuevas van en `backoffice/`, protegidas con `staff_required`/`superuser_required`.

## D12. Documentación viva

- **Decisión**: docstring obligatorio en español (CI), web MkDocs generada del código, changelog en `docs/novedades.md`,
  y este índice para asistentes (`ZYRA_CONTEXT.md` + `docs/ai/`).
- **Motivo**: `docs/mantener-documentacion.md`.
- **Consecuencias**: `docs/ai/` no está en la navegación de `mkdocs.yml` (se construye pero no se enlaza en el menú).
  El índice se consulta con `grep` (columna *Claves* con sinónimos) más que leyéndolo entero, porque así lo usan
  los asistentes; `scripts/check_ai_docs.py` en CI evita que se quede desfasado.

## D13. Etiqueta «Capitán» sobre el valor `admin`

- **Decisión**: `Membership.ADMIN = "admin"` se muestra como «Capitán» (`core/models.py`).
- **Motivo**: cambio de nombre en la interfaz; el valor guardado se mantuvo. Por qué no se migró: no documentado.
- **Consecuencias**: en código se sigue usando `is_admin` / `club_admin_required`.

## Documentación del repositorio desfasada respecto al código

Comprobado el 09/10/2026; manda el código:

| Dónde | Dice | El código hace |
|---|---|---|
| `Readme.md` § Multi-club | Roles «Administrador» / «Miembro» | La etiqueta es «Capitán» (`core/models.py`) |
| `Readme.md` § Multi-club | Enlace de invitación de un solo uso | Enlace compartido de varios usos; solo vale el último (`core/views.py`, `create_invitation_link`) |
| `Readme.md` § Multi-club | Un usuario puede pertenecer a varios clubes | Un club por cuenta (`core.services.club_of`) |
| `Readme.md` § Completar equipo | Los existentes nunca se modifican | Actualiza los puntos SNP de los existentes (`players.snp_import.confirm`) |
| `Readme.md` § Informe automático | PDF de 2 páginas | Intenta 2; si no cabe, más páginas numeradas sobre el total real (`match/report_pdf.py`) |
