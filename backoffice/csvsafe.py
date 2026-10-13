"""Saneado de valores para ficheros CSV que se abrirán en Excel u otra hoja de cálculo."""

# Un texto que empieza por alguno de estos caracteres se interpreta como fórmula.
_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


def csv_safe(value):
    """
    Valor listo para escribir en un CSV: ``None`` pasa a vacío y un texto que empezaría una
    fórmula (``=HYPERLINK(...)``) lleva delante una comilla simple para que se lea como texto.
    Los números (también los negativos) no se tocan.
    """
    if value is None:
        return ""
    if isinstance(value, str) and value.startswith(_FORMULA_START):
        return "'" + value
    return value


def to_csv_text(columns, rows):
    """CSV que Excel abre bien en español (UTF-8 con BOM, separador «;»), con todos los valores saneados."""
    import csv
    import io
    out = io.StringIO()
    out.write("﻿")
    writer = csv.writer(out, delimiter=";")
    writer.writerow([csv_safe(c) for c in columns])
    for row in rows:
        writer.writerow([csv_safe(v) for v in row])
    return out.getvalue()
