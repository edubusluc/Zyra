# Zyra

Aplicación web para gestionar equipos de pádel: jugadores, convocatorias,
partidos y estadísticas. Diseño oscuro con acento lima, responsive (barra de
navegación inferior en móvil).

El paquete de configuración de Django se llama `zyra` (antes `snp_gladiadores`):

- Ajustes: `zyra.settings`
- WSGI: `zyra.wsgi.application`

Los recursos de marca (logo, favicon, icono para móvil) están en `static/zyra/`.


## Puesta en marcha

### Configuración (`.env`)

Todo lo que cambia entre tu ordenador y producción sale de variables de entorno o del
fichero `.env` junto a `manage.py` (no se sube a git). Copia `.env.example` como `.env`:

```bash
cp .env.example .env
```

- **En tu ordenador** basta con `DJANGO_DEBUG=True`.
- **En producción** (`DJANGO_DEBUG` sin definir o `False`) la aplicación **no arranca** si
  falta `DJANGO_SECRET_KEY` (mínimo 50 caracteres) o `FIELD_ENCRYPTION_KEY` (clave Fernet
  que cifra las cuentas SNP). Define también `DJANGO_ALLOWED_HOSTS`,
  `DJANGO_CSRF_TRUSTED_ORIGINS` y, si el hosting tiene un proxy que termina el https,
  `DJANGO_BEHIND_PROXY=True`. Activa solo https: redirección, cookies seguras y HSTS
  (1 hora por defecto; súbelo con `DJANGO_SECURE_HSTS_SECONDS`).

`.env.example` explica cada variable y cómo generar las claves. Para comprobar la
configuración de producción: `python manage.py check --deploy`.

### Base de datos y migraciones

Las migraciones **están en git** (antes cada entorno generaba las suyas). Ya no hace falta
`makemigrations` para desplegar: basta con

```bash
python manage.py migrate
```

Si cambias un modelo, genera la migración con `python manage.py makemigrations` y súbela
con el resto del cambio. El CI falla si un modelo cambia sin su migración.

**Bases de datos creadas antes de este cambio** (con migraciones generadas en local):

1. Haz una copia de seguridad de la base de datos.
2. **Antes de `git pull`**, borra tus ficheros de migración locales (todo lo que hay en
   `*/migrations/` salvo `__init__.py`); si no, git no puede traer los del repositorio.
3. Trae el código y ejecuta una sola vez:

```bash
python manage.py adopt_repo_migrations --dry-run   # muestra qué haría
python manage.py adopt_repo_migrations             # adapta el historial de migraciones
python manage.py migrate
```

`adopt_repo_migrations` comprueba antes que la base de datos tiene todas las tablas y
columnas de las migraciones del repositorio, y solo cambia el historial de migraciones
(ninguna tabla ni dato). Si le falta algo, se para y lo dice.

### Empezar de cero

```bash
python clear_database.py   # borra todas las tablas y las fotos subidas y aplica las migraciones
python populate_db.py      # opcional: carga el club LOS GLADIADORES con sus datos de partida
```

`clear_database.py` deja la base de datos vacía con el esquema actual (`--conservar-fotos`
no borra `media/`). `populate_db.py` pregunta el usuario, email y contraseña del capitán,
que se crea también como superusuario. No se puede deshacer: copia antes `db.sqlite3` y `media/`.

### PostgreSQL

Sin `DATABASE_URL` la aplicación usa SQLite (`db.sqlite3`), que basta para desarrollar.
En producción se usa PostgreSQL: define `DATABASE_URL` en el `.env`.

```
DATABASE_URL=postgres://usuario:contraseña@servidor:5432/zyra
```

**PostgreSQL en tu ordenador con Docker** (opcional, para probar como en producción):

```bash
docker run -d --name zyra-postgres -p 5432:5432 \
  -e POSTGRES_USER=zyra -e POSTGRES_PASSWORD=zyra -e POSTGRES_DB=zyra \
  -v zyra-postgres:/var/lib/postgresql/data postgres:16
```

Y en el `.env`: `DATABASE_URL=postgres://zyra:zyra@localhost:5432/zyra`. Para volver a
SQLite basta con quitar (o comentar) esa línea. `docker stop zyra-postgres` lo para y
`docker start zyra-postgres` lo vuelve a arrancar con los datos.

**Pasar los datos de SQLite a PostgreSQL** (una sola vez):

1. El SQLite tiene que estar al día: sin `DATABASE_URL`, `python manage.py migrate`
   (y antes `adopt_repo_migrations` si es una base de datos antigua).
2. Con `DATABASE_URL` apuntando a un PostgreSQL **vacío**:

```bash
python manage.py migrate                               # crea las tablas en PostgreSQL
python manage.py copy_sqlite_to_db                     # o: copy_sqlite_to_db ruta/a/otro.sqlite3
```

`copy_sqlite_to_db` copia todo en una sola transacción (o todo o nada), no modifica el
SQLite y al final cuenta las filas de cada tabla en los dos lados; si alguna no coincide,
lo dice. Se niega a copiar sobre un PostgreSQL que ya tenga datos. Las contraseñas, las
sesiones y los enlaces con Google se copian tal cual; la cuenta SNP también, siempre que
`FIELD_ENCRYPTION_KEY` sea la misma.

### Logs y errores

Los logs (incluidos los errores 500 con su traza) salen por la salida estándar, que
recoge gunicorn o el hosting. El nivel se cambia con `DJANGO_LOG_LEVEL`. Opcionalmente,
con `SENTRY_DSN` los errores se envían a Sentry.

### Tests y CI

```bash
DJANGO_DEBUG=True python manage.py test
```

GitHub Actions (`.github/workflows/tests.yml`) ejecuta en cada PR y en `main`, con SQLite
y con PostgreSQL: que no falten migraciones, todos los tests y `check --deploy` con una
configuración de producción.


## Multi-club

La aplicación gestiona varios clubes. Cada club (`core.Club`) tiene sus propios jugadores,
equipos rivales, partidos, convocatorias y estadísticas, y sus usuarios
(`core.Membership`) solo pueden ver los datos de los clubes a los que pertenecen.

- **Administrador**: gestiona jugadores, equipos, partidos, convocatorias y miembros.
- **Miembro**: solo consulta.

Un club nuevo se registra desde `/core/register_club/`. Desde *Miembros del club*
(`/core/members/`) los administradores pueden:

- **Invitar por email**: el jugador recibe un enlace de un solo uso, válido 24 horas,
  para registrarse (usuario, email y contraseña, o con Google) y entrar como miembro.
  Si ya tiene cuenta, inicia sesión y se une con un clic. Los capitanes no crean
  cuentas: cada jugador crea la suya.
- **Generar un enlace de invitación** para copiarlo o compartirlo por WhatsApp, con
  las mismas condiciones (un solo uso, 24 horas).
- Cambiar el email y el rol de los miembros, o quitarlos del club.

En los formularios con contraseña hay un botón para mostrarla, y al crear una se
muestra la lista de requisitos que se va marcando mientras se escribe.

Se puede iniciar sesión con el usuario o con el email. Al registrarse (con invitación o
creando un club) se envía un correo de bienvenida con el usuario, el equipo y sus
administradores. Si un usuario pertenece a varios clubes, elige el
activo con el selector de la barra superior.

### Actualizar una base de datos existente

```bash
python manage.py migrate
# Crea el club "LOS GLADIADORES", le asigna todos los datos existentes
# y da de alta a los usuarios actuales como administradores.
python manage.py assign_default_club --name "LOS GLADIADORES"
```

### Partidos duplicados y restricciones de integridad

Desde esta versión la base de datos impide que un enfrentamiento tenga dos
partidos con el mismo número o que un partido tenga dos resultados. Si tu base
de datos ya tiene duplicados, límpialos **antes** de migrar:

```bash
python manage.py fix_duplicate_games --dry-run   # muestra qué se borraría
python manage.py fix_duplicate_games             # conserva el que tiene resultado o el más reciente
python manage.py migrate
```

### Portada y ubicación de los partidos

La portada muestra el escudo del equipo propio, el próximo partido (con enlace a
Google Maps) y el jugador y la pareja con la racha de victorias activa más larga.
El módulo de publicaciones ya no existe.

Cada partido guarda una **copia** de la ubicación del equipo local al crearse
(`Match.location`): si el equipo cambia de sede, los partidos ya creados no cambian.
Para rellenar los partidos que ya existían:

```bash
python manage.py migrate
python manage.py fill_match_locations
```

Las tablas antiguas de publicaciones (`post_post`, `post_image`) quedan en la base
de datos sin uso; se pueden borrar a mano si se quiere.

## Identificadores públicos

Como en Salesforce, cada objeto tiene un identificador público de 15 caracteres:
un prefijo de 3 letras que dice qué es y 12 caracteres aleatorios. Es el que aparece
en las URLs y en los filtros de estadísticas, así no se ven números consecutivos
(`/players/player_details/PLYa8Kd02LmQx7Z/` en vez de `/players/player_details/2/`).
El id numérico sigue siendo la clave interna de la base de datos y de las relaciones.

| Prefijo | Objeto | Prefijo | Objeto |
| --- | --- | --- | --- |
| `CLB` | Club | `MAT` | Enfrentamiento |
| `MBR` | Miembro | `GAM` | Partido |
| `INV` | Invitación | `RES` | Resultado |
| `TEA` | Equipo | `CAL` | Convocatoria |
| `PLY` | Jugador | `LOG` | Registro de convocatoria |
| `SNA` | Cuenta SNP | `PEN` | Penalización |
| `SNH` | Histórico de puntos SNP | `IMP` | Importación (back-office) |
| `SNI` | Completar equipo | `RUN` | Ejecución de proceso (back-office) |
| | | `QRY` | Consulta guardada (back-office) |

Los objetos nuevos lo reciben al guardarse (`core/public_id.py`). Los enlaces antiguos
con números dejan de funcionar (dan 404). Las páginas de usuarios del back-office
siguen usando el id de Django.

### Desplegar esta versión

```bash
python manage.py migrate
# Da un identificador a todas las filas que ya existían (se puede repetir sin riesgo)
python manage.py assign_public_ids
```

## Informe automático al cerrar una convocatoria

Al cerrar una convocatoria se genera un PDF (2 páginas, estilo Zyra) y se envía
por email a los **administradores del club que tengan email** (se configura en
*Miembros*). Incluye el rendimiento de convocados y parejas como local o
visitante según el partido, jugadores en racha, precedentes contra el rival y
dos alineaciones recomendadas según el formato de la SNP. También se puede
descargar desde el detalle del partido (botón *Informe PDF*).

Los informes se envían desde **join.zyra@gmail.com** (Gmail ya viene
configurado). Solo falta la contraseña de aplicación de esa cuenta, que nunca
se guarda en el código: defínela como variable de entorno (o en `.env`):

```
EMAIL_HOST_PASSWORD=contraseña_de_aplicación_de_16_letras
```

La contraseña de aplicación se crea en la cuenta de Google de join.zyra@gmail.com:
Seguridad → Verificación en dos pasos → Contraseñas de aplicaciones.

Sin `EMAIL_HOST_PASSWORD` los correos se muestran en la consola (útil en desarrollo).

Cada envío queda registrado (`call.ReportDelivery`, uno por destinatario) y hace de
cola: se intenta enviar al cerrar la convocatoria y, si falla, el proceso programado
`send_call_reports` (cada 5 minutos) lo reintenta a los 2, 10, 30 y 120 minutos. Tras
5 intentos se da por fallido y el personal recibe el aviso de fallo del back-office.
Cada correo sale por separado: si falla un destinatario, los demás lo reciben igual.
La convocatoria se cierra siempre, el detalle del partido muestra el estado del envío
y el botón *Reenviar informe* lo vuelve a mandar. `EMAIL_MAX_PER_RUN` (100) limita los
correos de cada pasada. Gmail admite unos 500 correos al día: con muchos clubes conviene
un proveedor de correo transaccional (Brevo, Amazon SES, Postmark…), que se configura
solo con `EMAIL_HOST`, `EMAIL_HOST_USER` y `EMAIL_HOST_PASSWORD`.

## Inicio de sesión con Google

Se usa [django-allauth](https://docs.allauth.org/). El botón de Google solo aparece
si están definidas las variables de entorno `GOOGLE_CLIENT_ID` y `GOOGLE_CLIENT_SECRET`
(o en `.env`); nunca van en el código.

1. En [Google Cloud Console](https://console.cloud.google.com/) abre *Google Auth Platform*:
   - *Información de la marca*: nombre Zyra y correo de asistencia join.zyra@gmail.com.
   - *Público*: tipo *Externo* y **Publicar app** para que pueda entrar cualquier cuenta de Google.
   - *Acceso a los datos*: permisos `openid`, `userinfo.email` y `userinfo.profile`.
2. En *Clientes → Crear cliente*, tipo *Aplicación web*:
   - Origen autorizado: `http://127.0.0.1:8000`
   - URI de redirección autorizado: `http://127.0.0.1:8000/accounts/google/login/callback/`
   - Al desplegar, añade también el origen `https://<tu-dominio>` y el URI
     `https://<tu-dominio>/accounts/google/login/callback/`.
3. Copia el ID y el secreto al `.env` (junto a `manage.py`) y reinicia el servidor.

Si alguien entra con Google y ya existe una cuenta con ese email, entra en esa cuenta.

### Completar equipo

Con la cuenta SNP registrada, la lista de jugadores muestra a los administradores el
botón **Completar equipo**: lee los jugadores del equipo en SNP y abre una ventana con
los que se van a añadir y los que no porque ya están en Zyra (mismo criterio de nombres
que la actualización de puntos). Al confirmar solo se crean jugadores nuevos; los
existentes nunca se modifican. Desde la web se puede hacer una vez al mes. El staff lo
lanza sin ese límite desde el back-office (proceso `complete_snp_team`, pide el id `TEA...` del
equipo, que aparece en la ficha del club) o con
`python manage.py complete_snp_team <id del equipo> [--dry-run]`.

### Desplegar esta versión

```bash
pip install -r requirements.txt   # instala django-allauth
python manage.py migrate          # crea core_invitation y las tablas de allauth
```

## Puntos SNP automáticos

Cada administrador guarda en *Menú → Cuenta SNP* el usuario y la contraseña de SNP
(snpgalaxy.com) de su capitán y, solo si la cuenta tiene varios equipos, el número del
equipo. Usuario y contraseña se guardan cifrados (`core/crypto.py`). El proceso
programado `update_snp_scores` recorre los clubes, entra
en SNP con su cuenta, navega Series Nacionales → el país de la nacionalidad del equipo (España si no tiene) → Mis equipos → el equipo, lee
los puntos de los jugadores (`players/scraper.py`) y actualiza los «Puntos SNP». Los
nombres se cruzan sin tener en cuenta mayúsculas, tildes, la categoría final (500,
Future) ni el segundo apellido si falta en un lado; lo que no encaja se muestra en la
página de la cuenta SNP. Cada actualización guarda además un punto en el histórico del
jugador (`SnpScoreHistory`), que se ve como gráfico en sus estadísticas. Mientras el club
no tenga cuenta SNP, la portada muestra a los administradores un aviso que lleva a
registrarla. Solo el staff puede lanzarlo a mano, desde el back-office
(*Ejecutar ahora*) o con `python manage.py update_snp_scores [--club "<nombre o slug>"] [--all] [--batch-size 50] [--headed]`
(`--headed` abre el navegador a la vista para seguir cada paso).

Cómo se reparte el trabajo y cómo se evita que SNP nos bloquee:

- **Ciclo semanal.** El ciclo empieza los lunes a las 23:00 y el proceso se lanza cada
  día a esa hora, pero solo hace los clubes pendientes del ciclo: los que aún no se han
  intentado y los que fallaron por algo pasajero (red, SNP lento o limitándonos). Los
  fallos de usuario o contraseña no se reintentan solos: repetir un inicio de sesión
  rechazado puede bloquear la cuenta del capitán. `--all` repite todos. Desde el
  back-office, *Con opciones…* permite lanzarlo con «Repetir todos los equipos»
  (`--all`), «Solo este club» (`--club`) y «Traza detallada» (`--verbosity=2`).
- **Lotes.** Los clubes van en lotes de `SNP_BATCH_SIZE` (50). Cada club se guarda en su
  propia transacción (todos sus jugadores o ninguno) y un error en uno no afecta a los
  demás. Cada lote usa un navegador nuevo y cada club una sesión aislada.
- **Ritmo.** Entre club y club hay una pausa aleatoria de `SNP_PAUSE_MIN_SECONDS` a
  `SNP_PAUSE_MAX_SECONDS` (5–15 s) y entre lotes `SNP_BATCH_PAUSE_SECONDS` (60 s). No se
  descargan imágenes, vídeos ni tipos de letra.
- **Freno.** Si SNP responde 429, 403 o 503, o fallan `SNP_MAX_CONSECUTIVE_FAILURES` (5)
  clubes seguidos por la red, el proceso para y avisa al personal. Los que faltan van
  primero en la pasada siguiente.

A ese ritmo cada club tarda de media unos 30–40 s. 1.000 clubes son unas 10 horas y
10.000, unos 4 o 5 días, dentro de la semana del ciclo.

Define una clave de cifrado propia en `.env` (obligatoria en producción; si la cambias,
las cuentas guardadas dejan de poder leerse y hay que volver a introducirlas):

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# FIELD_ENCRYPTION_KEY=<la clave que imprime>
```

### Desplegar esta versión

```bash
pip install -r requirements.txt   # añade cryptography
playwright install chromium       # navegador que usa el scraper
python manage.py migrate          # crea players_snpaccount y players_snpscorehistory
```

## Idiomas (español e inglés)

La web sale en español. El selector de idioma de la cabecera (y del back-office) permite
verla en inglés; la elección se guarda en una cookie, así que se mantiene entre visitas.
No se mira el idioma del navegador: sin elegir nada, todo sale en español.

Los textos se escriben en español en el código (`{% translate %}` / `{% blocktranslate %}`
en las plantillas, `gettext` en Python y en `static/js`), y la traducción al inglés está en
`locale/en/LC_MESSAGES/django.po` (páginas, formularios y mensajes) y `djangojs.po` (textos
de los ficheros JavaScript). Los `.mo` compilados también están en git, así que para
arrancar no hace falta nada más.

Si añades o cambias textos, necesitas `gettext` instalado (`brew install gettext`,
`apt install gettext`, o en Windows los binarios de gettext para Windows):

```bash
python manage.py makemessages -l en -d django --no-obsolete -i "*/tests*.py"
python manage.py makemessages -l en -d djangojs --no-obsolete
# traduce en los .po las entradas con msgstr "" (y quita las marcadas "fuzzy")
python manage.py compilemessages -l en
```

Los correos y el PDF de la convocatoria salen en el idioma de quien hace la acción en la
web; los que envían los procesos programados salen en español.

## Correos

Todos los correos salen de join.zyra@gmail.com con el mismo pie corporativo (logo de
Zyra y contacto), montado en `core/emails.py` y `core/templates/emails/layout.html`.
El logo va incrustado en el propio correo (`static/zyra/email-logo.png`).
Los de allauth (recuperar contraseña) usan el mismo diseño: `core.adapters.AccountAdapter.render_mail`
mete en el layout el `*_message.html` de `core/templates/account/email/`.

## Back-office

Panel para el dueño de la plataforma en `/backoffice/`: dashboard con KPIs de todos los
clubes, listado y ficha de clubes y de usuarios. Solo entra el personal de Zyra
(usuarios con `is_staff`); al resto se le responde 404. Los usuarios staff ven el
enlace *Back-office* en el menú de usuario. La consola SQL y la
importación de datos son solo para superusuarios.

Para darte acceso a ti mismo:

```bash
python manage.py createsuperuser        # si aún no tienes superusuario
# o, con un usuario que ya existe:
python manage.py shell -c "from django.contrib.auth.models import User; User.objects.filter(username='TU_USUARIO').update(is_staff=True)"
```

El Django admin queda como herramienta de emergencia **solo para superusuarios**. Su
ruta es `/admin/` por defecto; en producción conviene cambiarla por una menos obvia
con la variable de entorno `ADMIN_URL` (por ejemplo `ADMIN_URL=gestion-9f3k/`, con la
barra final).

### Carga y usuarios conectados

La página *Carga y conectados* (`/backoffice/load/`) y el KPI *Conectados ahora* del
dashboard salen de `backoffice.middleware.ActivityMiddleware`, que:

- apunta la última actividad de cada usuario con sesión (como mucho una vez por minuto;
  cuenta como conectado si ha hecho algo en los últimos 5 minutos y se borra al cerrar
  sesión);
- suma por minuto las peticiones, el tiempo de respuesta, las lentas (más de 1 s) y los
  errores 500. Los estáticos no cuentan. Cada proceso acumula en memoria y vuelca a la
  base de datos cada 15 segundos.

Las métricas de más de 30 días las borra cada noche el proceso programado
`purge_request_metrics`.

### Procesos programados

Los procesos se definen en `backoffice/jobs.py`: cada uno es un comando de Django con
su horario en formato cron (hora de Madrid). Para añadir uno, crea el comando y añade
una entrada a `JOBS`. En *Back-office → Procesos* se ven todos, con su última y
próxima ejecución, y se pueden pausar o ejecutar a mano. Cada ejecución queda en el
log con su salida y, si falla, el error; además se envía un email al personal de Zyra.

Un único lanzador ejecuta lo que toca. **El servidor tiene que llamarlo cada minuto**;
si no lo hace, el back-office avisa de que el lanzador no está en marcha:

```bash
python manage.py run_scheduler
```

Con cron, por ejemplo (ajusta las rutas):

```
* * * * * cd /ruta/a/Zyra && /ruta/a/python manage.py run_scheduler >> /tmp/zyra-scheduler.log 2>&1
```

**Ejecutar ahora** no espera al lanzador: arranca el proceso en el momento y abre su
ficha con la **traza en directo** (se va guardando cada segundo, con la hora de cada
línea). Si el proceso ya está en marcha, no se lanza otra vez. Puedes cerrar la página:
la ejecución sigue y la traza queda en el log.

Mientras un proceso está en marcha da una **señal de vida cada minuto**. Nunca se lanza
una segunda copia mientras la primera siga viva, dure lo que dure (por ejemplo
`update_snp_scores` con muchos clubes). Si deja de dar señales durante 10 minutos (se
reinició o se cayó el servidor), la ejecución se marca como interrumpida y el proceso
vuelve a lanzarse en su siguiente hora programada, no al momento.

### Consola SQL

*Back-office → Consola SQL* (solo superusuarios) ejecuta consultas **de solo lectura**
sobre toda la base de datos, al estilo del Data Export de Salesforce:

- Solo una sentencia `SELECT` o `WITH`. La lectura la garantiza la base de datos:
  `PRAGMA query_only` en SQLite, transacción `READ ONLY` en PostgreSQL.
- Máximo 10 segundos por consulta, 500 filas en pantalla y 50.000 al exportar.
- Exporta a CSV (UTF-8 con `;`, se abre bien en Excel en español).
- Las contraseñas, sesiones y tokens no se pueden consultar y se ocultan en un `SELECT *`.
- Consultas guardadas, esquema de tablas a la vista y registro de todas las consultas
  lanzadas (quién, cuándo y cuántas filas).
- **Campos de los registros relacionados**, como en Salesforce: en una clave ajena se
  puede seguir con un punto. Por ejemplo
  `SELECT local_id, local_id.name, visiting.name FROM match_match LIMIT 100`
  (vale con o sin `_id`, con alias de tabla y hasta 4 saltos, p. ej.
  `local_id.club_id.name`). La consola lo convierte en `LEFT JOIN` y enseña el SQL
  ejecutado. En el esquema, las claves ajenas indican a qué tabla apuntan. No funciona
  dentro de subconsultas.
- **Autocompletado** mientras escribes: tablas tras `FROM`/`JOIN`, columnas de las tablas
  de la consulta (tras `SELECT`, una coma, `WHERE`…) y, al poner un punto tras una clave
  ajena (`local_id.`), los campos de la tabla relacionada. Flechas para elegir, Tab o
  Enter para insertar, Esc para cerrar y Ctrl + Espacio para abrir la lista a mano.

### Importar datos

*Back-office → Importar datos* (solo superusuarios) carga jugadores, equipos rivales o
partidos de un club desde un CSV: subir → emparejar columnas → previsualizar → confirmar.

- Modos: solo crear, solo actualizar o crear y actualizar. Los registros existentes se
  buscan por `id` o por su clave natural (nombre y apellidos, nombre del equipo).
- Cada fila pasa las validaciones del modelo; si alguna falla no se importa nada y se
  pueden descargar los errores.
- Cada importación queda en el historial y se puede **deshacer**.
- Edición masiva: exporta desde la consola SQL con la columna `id`, edita en Excel e
  importa en modo actualizar.

### Desplegar esta versión

```bash
python manage.py migrate          # crea las tablas del back-office
```

y programa `run_scheduler` cada minuto como se explica arriba.
