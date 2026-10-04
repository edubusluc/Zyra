# Funcionalidades

Qué puede hacer cada persona en Zyra. Los enlaces a la derecha llevan al código que lo implementa.

## Roles

| Rol | Quién es | Qué puede hacer |
|---|---|---|
| **Capitán** | Quien crea el club o a quien otro capitán da ese rol. | Todo lo de su club: jugadores, equipos, partidos, convocatorias, miembros, cuenta SNP. |
| **Miembro** | Jugador invitado al club. | Ver partidos, convocatorias, jugadores y estadísticas; enlazar su cuenta con su jugador y subir su foto. |
| **Personal** (staff) | Equipo de Zyra. | Back-office: métricas, clubes, usuarios, procesos, revisión de fotos. |
| **Superusuario** | Dueño de la plataforma. | Además, consola SQL, importación de datos y el admin de Django. |

Cada cuenta pertenece a un solo club: quien ya es miembro o capitán de uno no puede registrar
otro ni unirse a otro hasta que abandone el suyo (los clubes suspendidos no cuentan). Las cuentas
que ya estaban en varios clubes conservan el selector de club. Todos los datos se filtran por
el club activo: lo de otro club da 404. Sin permiso, la página «Sin permiso» explica por qué
([`core.decorators`](referencia/core/decorators.md)).

## Cuentas y clubes

- **Registro de club**: usuario, email y contraseña (requisitos en vivo y botón para verla) o con
  Google. La página se abre arriba, sin saltar a ningún campo. Crea el club, su equipo propio y deja a la persona como capitán
  ([`core.views.register_club`](referencia/core/views.md), [`core.services`](referencia/core/services.md)).
- **Entrar con Google**: si el email ya existe, entra en esa cuenta y no crea otra
  ([`core.adapters`](referencia/core/adapters.md)).
- **Inicio de sesión con freno**: demasiados intentos fallidos devuelven 429.
- **Miembros**: lista, cambio de rol, quitar del club (nunca el último capitán; su cuenta se
  desenlaza de su jugador), invitaciones por email (un solo uso) o por enlace compartido (lo
  pueden usar varias personas, con contador de cuántas se han unido; al generar uno nuevo el
  anterior deja de funcionar y solo se ve el último), ambas válidas 24 h;
  pendientes paginadas de 10 en 10 con buscador por email.
- **Abandonar el club**: desde el menú de usuario, con confirmación. La cuenta se desenlaza de su
  jugador (que se conserva) y el último capitán no puede irse sin nombrar a otro. Si el capitán
  es el único miembro, al irse se elimina el club con todos sus datos (equipos, jugadores,
  fotos, partidos, convocatorias, sanciones y cuenta SNP); el popup lo avisa y pide escribir el
  nombre del club para confirmar.
- **Suspensiones y emails bloqueados**: el personal puede suspender un club o una cuenta y bloquear
  emails para que no se registren ([`core.blocklist`](referencia/core/blocklist.md)).
- **Idioma**: español o inglés con el selector de la cabecera.

## Inicio del club

**Primeros pasos** para el capitán de un club nuevo: añadir un equipo de su grupo, invitar a sus
jugadores, crear un jugador y crear un partido. Cada paso se marca solo cuando el club ya lo tiene
y la lista desaparece al completarla o al cerrarla ([`core.onboarding`](referencia/core/onboarding.md)).
Los clubes que ya existían no la ven.

Próximo partido con cuenta atrás, jugador y pareja en racha de victorias (con enlace a sus
estadísticas) y aviso al capitán si el club no tiene cuenta SNP
([`core.views.home`](referencia/core/views.md)).

## Jugadores

- Alta, edición (foto incluida) y baja. Al borrar un jugador sus partidos se conservan con su nombre
  ([`players.views`](referencia/players/views.md)).
- Nombres siempre en mayúsculas; posición (derecha, revés, mixto) y si sigue en el equipo.
- **Plantilla**: marcar de una vez quién está en el equipo.
- **Mi jugador**: cada miembro enlaza su cuenta con su jugador y sube su foto. Al elegir quién es
  ve en lima los jugadores libres y apagados los ya enlazados, el buscador filtra mientras escribe
  y «Soy yo» pide confirmación con su nombre y apellidos. Las fotos se
  validan (opcionalmente con AWS Rekognition) y el personal las revisa
  ([`core.images`](referencia/core/images.md), [`core.moderation`](referencia/core/moderation.md)).
- **Cuenta SNP** del club, cifrada ([`core.crypto`](referencia/core/crypto.md)), para:
    - **Puntos SNP**: proceso diario que entra en snpgalaxy.com y actualiza los puntos de cada
      jugador, con histórico y gráfico ([`players.snp`](referencia/players/snp.md),
      [`players.scraper`](referencia/players/scraper.md)).
    - **Completar equipo**: trae de SNP los jugadores que faltan, para revisar y confirmar
      ([`players.snp_import`](referencia/players/snp_import.md)).

## Equipos

- Equipo propio y rivales con categoría (masculino o femenino), país y división
  (Future, 500, 1000, Grand Slam). No se repite un nombre dentro de la misma división y avisa
  de nombres parecidos ([`team`](referencia/team/index.md), [`core.similarity`](referencia/core/similarity.md)).
- Un equipo nuevo sale relleno con los datos del propio.
- **Gestionar equipos**: editar varios a la vez (en el grupo, división...).

## Partidos

El ciclo de un enfrentamiento ([`match.views`](referencia/match/views.md)):

1. **Crear partido**: competitivo (enfrentamiento, reto o play off) o amistoso; el equipo propio
   juega siempre como local o visitante; calendario propio de Zyra.
2. **Convocatoria**: elegir jugadores (con sus sanciones a la vista); se puede editar y cada
   cambio queda en el **registro de convocatoria** ([`callLog`](referencia/callLog/index.md)).
3. **Cerrar convocatoria** (mínimo 10 jugadores): envía el **informe PDF** a los capitanes; lo que
   falle se reintenta solo cada 5 minutos. El informe recomienda cómo formar las parejas según el
   historial del club ([`match.advisor`](referencia/match/advisor.md)) y cabe en dos páginas aunque la
   convocatoria sea grande: se compacta solo y, si aun así no cabe, sigue sin dejar huecos. También se puede descargar o
   reenviar ([`match.report_pdf`](referencia/match/report_pdf.md), [`match.notifications`](referencia/match/notifications.md)).
4. **Parejas**: 5 partidos; los dos primeros valen 3 puntos y el resto 2. Cada jugador se elige
   con un buscador que filtra al escribir o desde la lista desplegable (solo convocados que no
   están ya en otra pareja, con sus puntos SNP). A la derecha se ve en vivo el orden de juego por
   la suma de puntos SNP. Se pueden reordenar mientras el acta está abierta
   ([`match.lineup`](referencia/match/lineup.md)).
5. **Resultados** por sets, con validación ([`match.scoring`](referencia/match/scoring.md)).
6. **Cerrar actas**: con los 5 resultados, calcula los puntos y el ganador; si la eliminatoria
   queda empatada a puntos (6-6), el partido queda como **empate**. Un partido cerrado ya no se
   puede cambiar ni borrar.

- **Sanciones**: advertencias a jugadores desde la convocatoria ([`penalty`](referencia/penalty/index.md)).
- Lista de partidos con resumen de ganados, empatados, perdidos y pendientes, y la temporada de
  cada partido. Selector de temporada: la actual por defecto, «Todas», las tres más recientes y un
  buscador para las más antiguas.
- En el detalle del partido la convocatoria va por posición en varias columnas; las posiciones con
  más de 8 jugadores muestran primero los que juegan y el resto con «Ver N más».

## Estadísticas

Todas con filtro Todos / Competitivos / Amistosos y selector de temporada
([`data_analyse.views`](referencia/data_analyse/views.md), [`data_analyse.pairs`](referencia/data_analyse/pairs.md)):

- **Equipo**: victorias, empates y derrotas (en total y por temporada), local / visitante,
  mejores jugadores y parejas, gráficos.
- **Jugador**: balance, con quién juega mejor, grado de afinidad (en el equipo o incluyendo
  antiguos), evolución de puntos SNP.
- **Parejas**: mejores y peores parejas y detalle de una pareja (rachas, temporadas, últimos partidos).
- **Avisos**: sanciones por jugador y temporada.

## Back-office

Solo para el personal, en `/backoffice/` ([`backoffice`](referencia/backoffice/index.md)):

- Dashboard con KPIs, usuarios conectados y carga de la web por minuto.
- Clubes y usuarios, con suspensión y borrado de fotos.
- Revisión de fotos subidas.
- **Procesos programados** (cron, hora de Madrid) con historial y traza en directo:
  puntos SNP, envío de informes, completar equipo y limpiezas
  ([`backoffice.jobs`](referencia/backoffice/jobs.md), [`backoffice.scheduler`](referencia/backoffice/scheduler.md)).
- **Consola SQL** de solo lectura con autocompletado, relaciones con punto y exportación CSV
  (superusuario) ([`backoffice.sql`](referencia/backoffice/sql.md)).
- **Importación CSV** de jugadores, equipos y partidos, todo o nada y con deshacer
  ([`backoffice.importer`](referencia/backoffice/importer.md)).

## Comandos de mantenimiento

| Comando | Para qué |
|---|---|
| `run_scheduler` | Lanza los procesos programados; debe ejecutarse cada minuto en el servidor. |
| `update_snp_scores` | Actualiza los puntos SNP (lo lanza el programador). |
| `complete_snp_team` | Trae jugadores desde SNP para un club. |
| `send_call_reports` | Reintenta los informes de convocatoria pendientes. |
| `copy_sqlite_to_db` | Copia una base de datos SQLite a PostgreSQL. |
| `adopt_repo_migrations` | Adapta bases de datos antiguas a las migraciones del repositorio. |
| `move_photos_to_media` | Pasa fotos antiguas a `media/`. |
| `clear_database.py` / `populate_db.py` | Empezar de cero y cargar los datos de partida. |
