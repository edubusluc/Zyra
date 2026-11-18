"""
Genera la «Referencia del código» de la web de documentación a partir de los módulos de Python.

Lo ejecuta MkDocs (plugin gen-files) en cada build: recorre las aplicaciones, crea una página por
módulo con `::: modulo` (mkdocstrings lee sus docstrings) y el índice de navegación SUMMARY.md.
Un módulo nuevo aparece solo en la web sin tocar nada.
"""
from pathlib import Path

import mkdocs_gen_files

ROOT = Path(__file__).resolve().parent.parent

# Aplicaciones en el orden del menú, con el nombre que se muestra.
APPS = {
    "core": "Núcleo (clubes, usuarios, invitaciones)",
    "players": "Jugadores y SNP",
    "team": "Equipos",
    "match": "Partidos, convocatorias e informes",
    "call": "Convocatorias (modelo)",
    "callLog": "Registro de convocatorias",
    "penalty": "Sanciones",
    "data_analyse": "Estadísticas",
    "backoffice": "Back-office",
    "api": "API de la app iOS",
    "zyra": "Configuración del proyecto",
}
SCRIPTS = ["clear_database.py", "manage.py"]


def skip(path):
    """Migraciones, tests y __init__.py vacíos no tienen página."""
    if "migrations" in path.parts or "templates" in path.parts:
        return True
    if path.name.startswith("test"):
        return True
    return path.name == "__init__.py" and not path.read_text(encoding="utf-8").strip()


nav = mkdocs_gen_files.Nav()

for app, title in APPS.items():
    app_dir = ROOT / app
    index = Path("referencia", app, "index.md")
    with mkdocs_gen_files.open(index, "w") as fd:
        fd.write(f"# {title}\n\n")
        init = app_dir / "__init__.py"
        if init.exists() and init.read_text(encoding="utf-8").strip():
            fd.write(f"::: {app}\n    options:\n      members: false\n\n")
        fd.write("Módulos de esta aplicación:\n\n")
        modules = sorted(p for p in app_dir.rglob("*.py") if not skip(p) and p.name != "__init__.py")
        for p in modules:
            rel = p.relative_to(app_dir).with_suffix("")
            fd.write(f"- [`{app}.{'.'.join(rel.parts)}`]({'/'.join(rel.parts)}.md)\n")
    nav[(title,)] = f"{app}/index.md"

    for p in modules:
        rel = p.relative_to(ROOT).with_suffix("")
        dotted = ".".join(rel.parts)
        doc_path = Path("referencia", *rel.parts).with_suffix(".md")
        with mkdocs_gen_files.open(doc_path, "w") as fd:
            fd.write(f"# `{dotted}`\n\n::: {dotted}\n")
            if p.name == "urls.py":
                # urls.py importa las vistas con *: solo se documentan sus rutas.
                fd.write("    options:\n      members: [urlpatterns, app_name]\n")
        mkdocs_gen_files.set_edit_path(doc_path, p.relative_to(ROOT))
        nav[(title, *rel.parts[1:])] = Path(*rel.parts).with_suffix(".md").as_posix()

with mkdocs_gen_files.open("referencia/scripts.md", "w") as fd:
    fd.write("# Scripts de la raíz\n\n")
    for name in SCRIPTS:
        fd.write(f"::: {Path(name).stem}\n    options:\n      heading_level: 2\n\n")
nav[("Scripts de la raíz",)] = "scripts.md"

with mkdocs_gen_files.open("referencia/SUMMARY.md", "w") as fd:
    fd.write("* [Índice](index.md)\n")
    fd.writelines(nav.build_literate_nav())

with mkdocs_gen_files.open("referencia/index.md", "w") as fd:
    fd.write("# Referencia del código\n\n"
             "Generada desde los docstrings en cada build: una página por módulo.\n\n")
    for app, title in APPS.items():
        fd.write(f"- [{title}]({app}/index.md) · `{app}`\n")
    fd.write("- [Scripts de la raíz](scripts.md)\n")
