# Modelo de datos (para asistentes)

Solo lo necesario para entender el dominio y no romper datos. Para los campos completos, lee el
`<app>/models.py` correspondiente. Índice general: `ZYRA_CONTEXT.md`. Verificado contra `main` el 09/10/2026.

## Mapa de relaciones

```
User ─┬─< Membership >── Club ──1:1── SnpAccount
      │                   ├─< Team (is_own: uno por club) ─< Player ─< SnpScoreHistory
      └─< Player.user     ├─< Player (club + team propio)
                          ├─< Match >── Team local / Team visiting (nullable)
                          │     └─< Game (n_game 1..5, 4 FK a Player) ─< Result (uno por Game)
                          │     └─< Call (uno por Match) ─M2M─ Player
                          │            ├─< CallLog   ├─< Penalty >── Player   └─< ReportDelivery
                          ├─< Invitation, SnpTeamImport, PhotoCheck, BlockedEmail …
```

Todos los modelos de dominio heredan `core.public_id.PublicIdModel` (campo `public_id` = prefijo
de 3 letras + 12 aleatorios; tabla de prefijos en `Readme.md` § Identificadores públicos). El `pk`
entero sigue siendo la clave de los FK. Excepciones sin `public_id`: `backoffice.UserActivity`,
`RequestMetric`, `ScheduledJob`, `QueryLog`.

## Modelos por app

### core (`core/models.py`)

- **Club**: inquilino. `slug` único (autogenerado en `save()`), `suspended_at` (suspensión desde
  back-office, no borra nada), `onboarding_dismissed_at`. `club.own_team` → `Team(is_own=True)`.
- **Membership**: `user`, `club`, `role` ∈ {`admin` (etiqueta «Capitán»), `member`}. Única por
  (`user`, `club`). El valor guardado sigue siendo `admin` aunque la interfaz diga «Capitán».
- **Invitation**: `token` único, `email` (vacío = enlace), `reusable` (enlace compartido, varios
  usos), `use_count`, `expires_at` (24 h, `INVITATION_TTL`). `Invitation.objects.pending()`.
- **PhotoCheck** (`approved`/`rejected`/`unchecked`), **PhotoRemoval**, **BlockedEmail** (`email`
  único, normalizado por `core/blocklist.py`): moderación. FKs con `SET_NULL` para conservar el registro.

### team (`team/models.py`)

- **Team**: `club`, `is_own` (máx. uno por club: `unique_own_team_per_club`), `in_group`,
  `gender` (`M`/`F`), `country`, `division` (`future`/`500`/`1000`/`grand_slam`), `location`, `photo`.
  `Team.save()` propaga `gender` a sus jugadores. La unicidad de nombre por división NO está en BD:
  la hace `team/forms.py` `Teamform.clean`.

### players (`players/models.py`)

#### Player

- `club` y `team` (siempre el equipo propio; `save()` lo asigna si falta y copia `gender`).
- `user` (enlace a la cuenta, `SET_NULL`); única por (`club`, `user`) cuando no es nulo.
- `in_team` (False = ya no está en la plantilla, se conserva para estadísticas), `snp_score`,
  `joined_season` (`AAAA-AAAA`), `position`, `skillfull_hand` (sic).
- Mostrar siempre `full_name` / `short_name` (mayúsculas); lo guardado no se toca.
- Temporada: de septiembre a agosto (`SEASON_START_MONTH = 9`, `current_season()`).

#### SNP

- **SnpAccount**: 1:1 con `Club`; `username_encrypted` / `password_encrypted` (Fernet,
  `core/crypto.py`); estado de la última sincronización (`last_sync_*`).
- **SnpScoreHistory**: un punto por jugador y día (`unique_snp_score_per_player_day`).
- **SnpTeamImport**: búsqueda de «Completar equipo»; `status` ∈ running/ready/error/done/cancelled,
  `source` web/backoffice, listas JSON `to_add`, `existing`, `created_players`.

### match (`match/models.py`)

- **Match**: `club`, `local`, `visiting` (FK a `Team`, nullable), `start_date`, `match_type`
  (`enfrentamiento`/`reto`/`playoff`/`amistoso`), `draft_mode` (True = acta abierta), `result`
  (`Victoria Local`/`Victoria Visitante`/`EMPATE`/`NONE`), `result_points` (`"7/5"`; formato
  antiguo `"7-5"`, ver `match.views.split_points`), `season` y `location` (rellenos en `save()` solo
  si están vacíos; `location` es copia, no enlace), `rival_name` (amistoso con rival escrito a mano:
  ese lado queda `NULL`). Usar `local_name`, `visiting_name`, `rival_label`, `own_is_local`, nunca `match.local.name` a pelo.
- **Game**: `match`, `n_game` 1..5 (único por match + `CheckConstraint`), `player_1/2_local`,
  `player_1/2_visiting` (`SET_NULL`), `removed_player_names` (JSON), `score` (3 en partidos 1–2,
  2 en 3–5, `match.lineup.game_points`), `winner` (`Local`/`Visitante`), `draft_mode`.
  Solo se rellenan los jugadores del lado del equipo propio. `save()` llama a `clean()`.
- **Result**: uno por `Game` (`unique_result_per_game`; el FK se llama `results` pese a ello),
  sets `set1..3_local/visiting` (set 3 nullable). `save()` valida con `match/scoring.py` y normaliza el set 3.

### call, callLog, penalty

- **Call** (`call/models.py`): una por `Match` (`unique_together`), M2M `players`, `draft_mode`
  (True = abierta).
- **ReportDelivery**: cola de envío del PDF, única por (`call`, `email`); `status`
  pending/sent/failed, `attempts`, `next_attempt_at`.
- **CallLog** (`callLog/models.py`): `text` con líneas separadas por `;`.
- **Penalty** (`penalty/models.py`): advertencia; `player`, `call`, `reason` (texto libre).

### backoffice (`backoffice/models.py`)

`UserActivity` (1:1 user), `RequestMetric` (una fila por minuto), `ScheduledJob` (estado de cada
proceso de `backoffice/jobs.py`, `running_since`, `heartbeat_at`), `JobRun` (salida y estado de cada
ejecución), `SavedQuery`, `QueryLog`, `ImportJob` (permite deshacer importaciones).

## Trampas de `related_name`

Nombres heredados que confunden al leer consultas [V]:

| Relación | Acceso inverso real |
|---|---|
| `Player.team` | `team.team` (jugadores del equipo) |
| `Call.match` | `match.match` (convocatorias del partido) |
| `Call.players` | `player.players` (convocatorias del jugador) |
| `Penalty.player` / `Penalty.call` | `player.player` / `call.call` |
| `Game.player_1_local` … | `player.player_1_local`, etc. |
| `Result.game` | `game.results` (aunque solo hay uno) |

Renombrarlos exige migración y tocar vistas, estadísticas, plantillas y `populate_db.py`.

## Borrados en cascada (qué se pierde)

- Borrar **Club** (`core.services.delete_club`) borra equipos, jugadores, partidos, convocatorias,
  advertencias, cuenta SNP, invitaciones y membresías; las cuentas de usuario se conservan. [V]
- Borrar **Player**: los `Game` se conservan (`SET_NULL` + señal `keep_name_in_games` en
  `match/models.py`); se pierden sus `Penalty`, `SnpScoreHistory` y su presencia en convocatorias. [V]
- Borrar **Team** rival borra en cascada sus `Match` (FK `CASCADE`). [V] No hay vista de borrado de
  equipos en `team/views.py`. [V]
- Borrar **Match** borra `Game`, `Result`, `Call`, `CallLog`, `Penalty`, `ReportDelivery`. Solo se
  permite con el acta abierta (`match.views.delete_match`). [V]

## Al modificar datos

- Cambio de modelo → `makemigrations` y subir la migración en el mismo PR (CI lo comprueba).
- Datos existentes: hay comandos de relleno de migraciones pasadas (`assign_public_ids`,
  `fill_match_locations`, `fix_duplicate_games` con `--dry-run`, `assign_default_club`). Solo
  `assign_public_ids` se documenta como repetible sin riesgo (`Readme.md`); lee los demás antes de reutilizarlos.
- `bulk_create` asigna `public_id` gracias a `PublicIdQuerySet`; `QuerySet.update()` no ejecuta
  `save()` (ni `clean()`, ni el relleno de `season`/`location`, ni la propagación de `gender`).
- `populate_db.py` crea filas con `public_id` explícitos: si cambias un modelo, revisa ese script.
