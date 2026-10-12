"""
Comprueba que el índice para asistentes (ZYRA_CONTEXT.md, CLAUDE.md y docs/ai/) sigue al día.

Lo ejecuta el CI (.github/workflows/docs.yml). Falla con código 1 y la lista de problemas si:

- una ruta citada entre comillas invertidas (`ruta/archivo.ext` o `carpeta/`) no existe;
- un archivo de static/js/ o un fichero de tests no aparece en ZYRA_CONTEXT.md;
- un comando de gestión (<app>/management/commands/) no aparece ni en ZYRA_CONTEXT.md ni en docs/ai/.

Así, quien añade una pantalla, un JS, un test o un comando sin apuntarlo en el índice se entera en
el propio PR, y el índice no se queda desfasado en silencio.

    python scripts/check_ai_docs.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "ZYRA_CONTEXT.md"
DOCS = [INDEX, ROOT / "CLAUDE.md", *sorted((ROOT / "docs" / "ai").glob("*.md"))]
APPS = ["backoffice", "call", "callLog", "core", "data_analyse", "match", "penalty", "players", "team"]
PATH_RE = re.compile(r"`([A-Za-z_][A-Za-z0-9_./-]*(?:\.(?:py|md|html|yml|toml|txt|css|js|po)|/))`")


def cited_paths(text):
    """Rutas entre comillas invertidas que parecen archivos o carpetas del repositorio."""
    for match in PATH_RE.finditer(text):
        path = match.group(1)
        # «migrations/» o «media/» son nombres genéricos, no rutas de este repositorio.
        if path.endswith("/") and path.count("/") == 1:
            continue
        yield path


def missing_paths():
    """Rutas citadas en los documentos que no existen en el repositorio."""
    out = []
    for doc in DOCS:
        for path in sorted(set(cited_paths(doc.read_text(encoding="utf-8")))):
            if not (ROOT / path).exists():
                out.append(f"{doc.relative_to(ROOT)}: no existe `{path}`")
    return out


def test_files():
    """Ficheros de tests de las apps (tests.py, tests_*.py, test_*.py)."""
    for app in APPS:
        for path in sorted((ROOT / app).glob("test*.py")):
            yield path.relative_to(ROOT).as_posix()


def uncovered():
    """JS, tests y comandos que existen pero el índice no menciona."""
    index = INDEX.read_text(encoding="utf-8")
    everything = "\n".join(doc.read_text(encoding="utf-8") for doc in DOCS)
    out = []
    for js in sorted((ROOT / "static" / "js").glob("*.js")):
        rel = js.relative_to(ROOT).as_posix()
        if rel not in index:
            out.append(f"ZYRA_CONTEXT.md: falta `{rel}` en la fila de su área")
    for rel in test_files():
        if rel not in index:
            out.append(f"ZYRA_CONTEXT.md: falta `{rel}` en la columna Tests de su área")
    for app in APPS:
        for cmd in sorted((ROOT / app / "management" / "commands").glob("*.py")):
            if cmd.stem != "__init__" and cmd.stem not in everything:
                out.append(f"docs/ai/workflows.md: falta el comando `{cmd.stem}` ({app})")
    return out


def main():
    """Imprime los problemas y sale con 1 si hay alguno."""
    problems = missing_paths() + uncovered()
    for line in problems:
        print(line)
    if problems:
        print(f"\n{len(problems)} problema(s) en el índice para asistentes.")
        return 1
    print("Índice para asistentes al día.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
