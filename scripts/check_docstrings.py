"""
Comprueba que todo módulo, clase y función del código de la aplicación tiene docstring.

Lo ejecuta el CI (.github/workflows/docs.yml) para que la documentación generada desde el código
(mkdocs.yml) no se quede atrás. Quedan fuera las migraciones, los tests, los `class Meta` y los
`__init__.py` vacíos. Sale con código 1 y la lista de lo que falta si hay algo sin documentar.

    python scripts/check_docstrings.py
"""
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APPS = ["backoffice", "call", "callLog", "core", "data_analyse", "match", "penalty", "players", "team", "zyra"]
SCRIPTS = ["clear_database.py", "manage.py", "scripts/check_docstrings.py", "scripts/check_ai_docs.py", "docs/gen_ref_pages.py"]
SKIP_CLASSES = {"Meta", "Media"}


def files():
    """Ficheros .py que se comprueban."""
    for app in APPS:
        for path in sorted((ROOT / app).rglob("*.py")):
            if "migrations" in path.parts or path.name.startswith("test"):
                continue
            yield path
    for name in SCRIPTS:
        yield ROOT / name


def missing(path):
    """Lista de «fichero:línea nombre» sin docstring en un fichero."""
    source = path.read_text(encoding="utf-8")
    if not source.strip():
        return []
    tree = ast.parse(source)
    rel = path.relative_to(ROOT)
    out = [] if ast.get_docstring(tree) else [f"{rel}:1 (módulo)"]
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name not in SKIP_CLASSES and not ast.get_docstring(node):
                out.append(f"{rel}:{node.lineno} {node.name}")
    return out


def main():
    """Imprime lo que falta y devuelve el código de salida."""
    problems = [item for path in files() for item in missing(path)]
    if problems:
        print(f"Faltan {len(problems)} docstrings:")
        print("\n".join(f"  {p}" for p in problems))
        return 1
    print("Todo el código tiene docstring.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
