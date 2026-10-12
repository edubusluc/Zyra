"""
Consola SQL del back-office: consultas de SOLO LECTURA sobre toda la base de datos.

La lectura está garantizada por la propia base de datos, no solo por este código:
- SQLite: la conexión se pone en ``PRAGMA query_only`` mientras dura la consulta.
- PostgreSQL: la consulta va en una transacción ``READ ONLY`` con ``statement_timeout``.
Además solo se admite una sentencia que empiece por SELECT o WITH, con límite de
filas y de tiempo, y los datos sensibles (contraseñas, sesiones, tokens) no se pueden
consultar ni aparecen en los resultados.
"""
import re
import time
from dataclasses import dataclass, field

from django.db import connection, transaction
from django.utils.translation import gettext as _

# Filas que se muestran en pantalla y que se exportan como máximo.
DISPLAY_LIMIT = 500
EXPORT_LIMIT = 50_000
# Longitud máxima de una consulta (acota el coste de las expresiones regulares que la analizan).
MAX_LENGTH = 20_000
# Tiempo máximo de una consulta.
TIMEOUT_SECONDS = 10

# Tablas que no aparecen en el esquema ni se pueden consultar.
HIDDEN_TABLES = {
    "django_session",
    "socialaccount_socialtoken",
    "socialaccount_socialapp",
    "account_emailconfirmation",
}
# Palabras que no pueden aparecer en la consulta: columnas sensibles y funciones
# peligrosas de SQLite.
BLOCKED_WORDS = HIDDEN_TABLES | {
    "password", "token", "secret", "session_key", "session_data",
    "load_extension", "readfile", "writefile", "edit", "fts3_tokenizer",
}
# Columnas del resultado cuyo valor se oculta aunque lleguen por un SELECT *.
MASKED_COLUMN = re.compile(r"password|token|secret|session", re.IGNORECASE)
MASK = "••••••"


class QueryError(ValueError):
    """Consulta no permitida o fallida; el mensaje se muestra tal cual en la consola."""
    pass


@dataclass
class QueryResult:
    """Resultado de una consulta: columnas, filas, si se cortó, duración y columnas ocultas."""
    columns: list
    rows: list
    truncated: bool
    duration_ms: int
    masked: list = field(default_factory=list)
    # SQL que se ha ejecutado de verdad, si es distinto del escrito (relaciones con punto).
    expanded_sql: str = ""

    @property
    def row_count(self):
        """Número de filas devueltas (como mucho el límite)."""
        return len(self.rows)


_COMMENTS = re.compile(r"--[^\n]*|/\*.*?\*/", re.DOTALL)
_STRINGS = re.compile(r"'(?:[^']|'')*'")


def clean(sql):
    """Quita comentarios, espacios y el punto y coma final."""
    sql = _COMMENTS.sub(" ", sql or "").strip()
    return sql[:-1].rstrip() if sql.endswith(";") else sql


def validate(sql):
    """Comprueba que la consulta es una única lectura y que no toca datos sensibles."""
    if len(sql or "") > MAX_LENGTH:
        raise QueryError(_("La consulta es demasiado larga (máximo %(max)s caracteres).") % {"max": MAX_LENGTH})
    sql = clean(sql)
    if not sql:
        raise QueryError(_("Escribe una consulta."))
    # Las comprobaciones se hacen sin el contenido de los textos entre comillas.
    code = _STRINGS.sub("''", sql)
    if ";" in code:
        raise QueryError(_("Solo se puede ejecutar una consulta cada vez."))
    first = code.split(None, 1)[0].lower()
    if first not in ("select", "with"):
        raise QueryError(_("Solo se admiten consultas de lectura (SELECT o WITH)."))
    words = set(re.findall(r"[a-z_][a-z0-9_]*", code.lower()))
    blocked = sorted(words & BLOCKED_WORDS)
    if blocked:
        raise QueryError(
            _("Esta consulta usa datos protegidos (%(words)s), que no se pueden consultar desde aquí.")
            % {"words": ", ".join(blocked)}
        )
    return sql


def run(sql, limit=DISPLAY_LIMIT, timeout=TIMEOUT_SECONDS):
    """Ejecuta una consulta de solo lectura y devuelve como mucho `limit` filas."""
    sql = validate(sql)
    written = sql
    sql = expand_relations(sql)
    start = time.monotonic()
    try:
        if connection.vendor == "sqlite":
            columns, rows, truncated = _run_sqlite(sql, limit, timeout)
        elif connection.vendor == "postgresql":
            columns, rows, truncated = _run_postgres(sql, limit, timeout)
        else:
            raise QueryError(_("La consola SQL no está preparada para %(vendor)s.") % {"vendor": connection.vendor})
    except QueryError:
        raise
    except Exception as exc:  # error de sintaxis, tabla inexistente, tiempo agotado...
        raise QueryError(_explain(exc, timeout)) from exc
    duration_ms = int((time.monotonic() - start) * 1000)

    masked = [i for i, name in enumerate(columns) if MASKED_COLUMN.search(name or "")]
    if masked:
        rows = [tuple(MASK if i in masked else v for i, v in enumerate(row)) for row in rows]
    return QueryResult(columns, rows, truncated, duration_ms, [columns[i] for i in masked],
                       expanded_sql=sql if sql != written else "")


def _fetch(cursor, limit):
    """Columnas y como mucho `limit` filas del cursor; pide una más para saber si hay más (truncado)."""
    columns = [c[0] for c in cursor.description or []]
    rows = cursor.fetchmany(limit + 1)
    return columns, [tuple(r) for r in rows[:limit]], len(rows) > limit


def _run_sqlite(sql, limit, timeout):
    """
    Ejecuta la consulta en SQLite con ``PRAGMA query_only`` y un manejador de progreso
    que la corta al pasar de `timeout` segundos.
    """
    connection.ensure_connection()
    raw = connection.connection
    deadline = time.monotonic() + timeout
    # El manejador de progreso corta la consulta si pasa del tiempo máximo.
    raw.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, 10_000)
    try:
        with connection.cursor() as cursor:
            cursor.execute("PRAGMA query_only = ON")
            try:
                cursor.execute(sql)
                return _fetch(cursor, limit)
            finally:
                cursor.execute("PRAGMA query_only = OFF")
    finally:
        raw.set_progress_handler(None, 0)


def _run_postgres(sql, limit, timeout):
    """Ejecuta la consulta en PostgreSQL en una transacción READ ONLY con statement_timeout."""
    with transaction.atomic(), connection.cursor() as cursor:
        cursor.execute("SET TRANSACTION READ ONLY")
        cursor.execute("SET LOCAL statement_timeout = %s", [int(timeout * 1000)])
        cursor.execute(sql)
        return _fetch(cursor, limit)


def _explain(exc, timeout):
    """Mensaje de error comprensible para una excepción de la base de datos (tiempo, escritura...)."""
    text = str(exc)
    if "interrupted" in text.lower() or "statement timeout" in text.lower():
        return _("La consulta tardó más de %(seconds)s segundos y se ha cancelado.") % {"seconds": timeout}
    if "readonly" in text.lower() or "read-only" in text.lower() or "query_only" in text.lower():
        return _("La consola es de solo lectura.")
    return _("Error en la consulta: %(error)s") % {"error": text}


def schema():
    """
    Tablas y columnas visibles, para la ayuda lateral de la consola. Las claves ajenas
    llevan la tabla a la que apuntan (para usar local_id.name).
    """
    models = _models_by_table()
    tables = []
    with connection.cursor() as cursor:
        for name in sorted(connection.introspection.table_names(cursor)):
            if name in HIDDEN_TABLES:
                continue
            model = models.get(name)
            columns = []
            for col in connection.introspection.get_table_description(cursor, name):
                if MASKED_COLUMN.search(col.name):
                    continue
                rel = _relation(model, col.name) if model else None
                target = rel.related_model._meta.db_table if rel and rel.column == col.name else ""
                columns.append({"name": col.name, "target": target})
            tables.append({"name": name, "columns": columns})
    return tables


# ---------- Relaciones con punto, como en SOQL ----------
#
#   SELECT local_id.name, visiting.location FROM match_match
#
# se convierte en
#
#   SELECT _r1.name AS "local_id.name", _r2.location AS "visiting.location"
#   FROM match_match
#   LEFT JOIN team_team _r1 ON _r1.id = match_match.local_id
#   LEFT JOIN team_team _r2 ON _r2.id = match_match.visiting_id
#
# El primer tramo puede ser la columna (local_id) o el nombre del campo (local), y se
# pueden encadenar varios saltos: local_id.club_id.name.

MAX_HOPS = 4
_PATH = re.compile(r"(?<![\w.\"])([A-Za-z_]\w*(?:\.[A-Za-z_]\w*){1,%d})(?![\w(])" % (MAX_HOPS + 1))
_SOURCE = re.compile(
    r"\b(?:from|join)\s+([A-Za-z_]\w*)(?:\s+(?:as\s+)?(?!(?:where|join|left|right|inner|outer|cross|full|natural|on|"
    r"using|group|order|limit|offset|having|union|window)\b)([A-Za-z_]\w*))?",
    re.IGNORECASE,
)
_CLAUSE_END = re.compile(r"\b(where|group\s+by|having|order\s+by|limit|offset|window)\b", re.IGNORECASE)


def _models_by_table():
    """Modelos de Django indexados por el nombre de su tabla (incluidas las tablas intermedias)."""
    from django.apps import apps
    return {m._meta.db_table: m for m in apps.get_models(include_auto_created=True)}


def _relation(model, name):
    """Campo ForeignKey/OneToOne de `model` que se llama `name` (por campo o por columna)."""
    for f in model._meta.concrete_fields:
        if f.is_relation and (f.many_to_one or f.one_to_one):
            if name.lower() in (f.name.lower(), f.column.lower()):
                return f
    return None


def _column(model, name):
    """Nombre de la columna de `model` que se llama `name` (por campo o por columna), o None."""
    for f in model._meta.concrete_fields:
        if name.lower() in (f.name.lower(), f.column.lower()):
            return f.column
    return None


def expand_relations(sql):
    """Convierte las rutas con punto sobre claves ajenas en LEFT JOIN. Si no hay ninguna, no cambia nada."""
    strings = []

    def stash(m):
        """Cambia un texto entre comillas por una marca para que no se analice; se restaura al final."""
        strings.append(m.group(0))
        return f"\x00{len(strings) - 1}\x00"

    code = _STRINGS.sub(stash, sql)
    models = _models_by_table()
    sources = {}  # alias o nombre de tabla -> (referencia en el SQL, modelo)
    for m in _SOURCE.finditer(code):
        table, alias = m.group(1), m.group(2)
        model = models.get(table) or models.get(table.lower())
        if model is None:
            continue
        ref = alias or table
        sources[ref.lower()] = (ref, model)
        sources.setdefault(table.lower(), (ref, model))

    joins, join_alias = [], {}
    replacements = []  # (inicio, fin, texto)

    for m in _PATH.finditer(code):
        parts = m.group(1).split(".")
        head = parts[0].lower()
        label = m.group(1)
        if head in sources:
            ref, model = sources[head]
            chain = parts[1:]
            label = ".".join(chain)
        else:
            owners = {(r, mod) for r, mod in sources.values() if _relation(mod, parts[0])}
            if not owners:
                continue  # no es una relación conocida: se deja tal cual
            if len(owners) > 1:
                raise QueryError(_("«%(path)s»: %(name)s existe en varias tablas; pon delante la tabla o su alias.") % {
                    "path": m.group(1), "name": parts[0],
                })
            ref, model = owners.pop()
            chain = parts
        if len(chain) < 2:
            continue  # tabla.columna normal
        for name in chain[:-1]:
            rel = _relation(model, name)
            if rel is None:
                raise QueryError(_("«%(path)s»: %(name)s no es una relación de %(table)s.") % {
                    "path": m.group(1), "name": name, "table": model._meta.db_table,
                })
            target = rel.related_model
            if target._meta.db_table in HIDDEN_TABLES:
                raise QueryError(_("«%(path)s»: %(table)s tiene datos protegidos.") % {"path": m.group(1), "table": target._meta.db_table})
            key = (ref.lower(), rel.column.lower())
            if key not in join_alias:
                alias = f"_r{len(joins) + 1}"
                join_alias[key] = alias
                joins.append(
                    f"LEFT JOIN {target._meta.db_table} {alias} "
                    f"ON {alias}.{rel.target_field.column} = {ref}.{rel.column}"
                )
            ref, model = join_alias[key], target
        column = _column(model, chain[-1])
        if column is None:
            raise QueryError(_("«%(path)s»: %(table)s no tiene la columna %(column)s.") % {
                "path": m.group(1), "table": model._meta.db_table, "column": chain[-1],
            })
        replacements.append((m.start(1), m.end(1), f"{ref}.{column}", label))

    if not joins:
        return sql
    if len(re.findall(r"\bselect\b", code, re.IGNORECASE)) > 1:
        raise QueryError(_("Las relaciones con punto (local_id.name) solo funcionan en consultas sin subconsultas."))

    # Con una sola tabla en el FROM, sus columnas sin tabla delante se cualifican para que
    # no choquen con las de las tablas añadidas (SELECT name, club.name FROM players_player).
    refs = {ref for ref, _ in sources.values()}
    if len(refs) == 1:
        (base_ref, base_model), = {v for v in sources.values()}
        columns = {f.column.lower() for f in base_model._meta.concrete_fields}
        taken = [(a, b) for a, b, _, _ in replacements]
        bare = re.compile(r"(?<![\w.\"])([A-Za-z_]\w*)(?![\w.(\"])")
        for m in bare.finditer(code):
            if m.group(1).lower() not in columns or any(a <= m.start() < b for a, b in taken):
                continue
            before = code[:m.start()].rstrip().lower()
            if before.endswith(" as") or before.endswith(("from", "join")):
                continue
            replacements.append((m.start(1), m.end(1), f"{base_ref}.{m.group(1)}", None))
        replacements.sort(key=lambda r: r[0])

    select_end = re.search(r"\bfrom\b", code, re.IGNORECASE).start()
    out, last = [], 0
    for start, end, text, original in replacements:
        out.append(code[last:start])
        # En la lista del SELECT, la columna del resultado se llama como se escribió.
        rest = code[end:select_end] if end <= select_end else ""
        if original and end <= select_end and not re.match(r"as\b", rest.lstrip(), re.IGNORECASE):
            text += f' AS "{original}"'
        out.append(text)
        last = end
    out.append(code[last:])
    code = "".join(out)

    from_pos = re.search(r"\bfrom\b", code, re.IGNORECASE).end()
    end_match = _CLAUSE_END.search(code, from_pos)
    at = end_match.start() if end_match else len(code)
    code = code[:at].rstrip() + "\n" + "\n".join(joins) + "\n" + code[at:]

    return re.sub("\x00(\\d+)\x00", lambda m: strings[int(m.group(1))], code).strip()
