# Mantener la documentación

La documentación vive en el repositorio y se publica sola. En cada pull request:

1. **Docstrings.** Toda función, clase y módulo nuevo lleva su docstring en español: qué hace y,
   si no es obvio, por qué. En las vistas, quién puede entrar y qué pasa con GET y POST.
   El CI lo comprueba (`python scripts/check_docstrings.py`) y falla si falta alguno.
2. **Funcionalidades.** Si cambia lo que ve o puede hacer un usuario, actualiza
   [Funcionalidades](funcionalidades.md) (`docs/funcionalidades.md`).
3. **Novedades.** Añade una línea arriba del todo en [Novedades](novedades.md)
   (`docs/novedades.md`) con el número de la pull request.

La [Referencia del código](referencia/index.md) no se escribe a mano: `docs/gen_ref_pages.py` crea
una página por módulo en cada build, y un módulo nuevo aparece solo.

## Cómo se publica

- `.github/workflows/docs.yml` construye la web en cada pull request (falla si un enlace o una
  referencia está rota, con `mkdocs build --strict`) y la publica en GitHub Pages en cada push a `main`.
- Dirección: <https://edubusluc.github.io/Zyra/>.
- Requisito (una sola vez): en GitHub, *Settings › Pages › Build and deployment › Source* tiene que
  estar en **GitHub Actions**.

## Verla en tu ordenador

```bash
pip install --only-binary :all: --require-hashes -r requirements-docs.txt
mkdocs serve          # http://127.0.0.1:8000, se recarga al guardar
python scripts/check_docstrings.py   # lista lo que falta por documentar
```

## Accesibilidad

Cada página nueva tiene que pasar `core/tests_accessibility.py` (corre en CI con el resto de
tests): añade su URL a la lista del test. Comprueba texto alternativo en las imágenes (`alt=""` solo
si la imagen es decorativa o el nombre ya está escrito al lado), un solo `<h1>` y encabezados sin
saltos (de `h1` a `h2`, no a `h4`), un título propio con `{% block page_title %}`, etiquetas en los
campos, iconos con `aria-hidden="true"` y gráficos `<canvas>` con `role="img"` y `aria-label`.

Para el contraste y lo que crea el JavaScript, con la web arrancada:

```bash
python scripts/auditoria_accesibilidad.py --usuario capitan --contrasena '...'          # escritorio
python scripts/auditoria_accesibilidad.py --usuario capitan --contrasena '...' --movil  # móvil
```
