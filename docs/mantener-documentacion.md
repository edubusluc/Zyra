# Mantener la documentación

La documentación vive en el repositorio y se publica sola. En cada pull request:

1. **Docstrings.** Toda función, clase y módulo nuevo lleva su docstring en español: qué hace y,
   si no es obvio, por qué. En las vistas, quién puede entrar y qué pasa con GET y POST.
   El CI lo comprueba (`python scripts/check_docstrings.py`) y falla si falta alguno.
2. **Funcionalidades.** Si cambia lo que ve o puede hacer un usuario, actualiza
   [Funcionalidades](funcionalidades.md) (`docs/funcionalidades.md`).
3. **Novedades.** Añade una línea arriba del todo en [Novedades](novedades.md)
   (`docs/novedades.md`) con el número de la pull request.
4. **Índice para asistentes.** Si cambian rutas, reglas de negocio, modelos o comandos, actualiza
   `ZYRA_CONTEXT.md` (raíz del repositorio) y el documento afectado de `docs/ai/`. Un JS, una
   plantilla principal o un test nuevo va a la fila de su área; el CI lo comprueba con
   `python scripts/check_ai_docs.py`.

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

## Guía de estilo de textos

Una sola página para que todas las pantallas hablen igual.

| Concepto | Se escribe | No se escribe |
|---|---|---|
| Cruce entre dos equipos (modelo `Match`) | **Enfrentamiento** | partido, encuentro |
| Cada una de las 5 parejas de un enfrentamiento (modelo `Game`) | **Partido 1-5** (en cursiva de apoyo: «pareja») | juego, game |
| Registrar quién juega con quién | **Alinear parejas** | crear partidos |
| Ver la lista de jugadores citados | **Convocatoria** / **Convocar** | llamada |
| Terminar un enfrentamiento | **Cerrar acta** | finalizar |
| Menú de equipo | **Club** (Miembros e invitaciones, Mi equipo, Rivales, Cuenta SNP) | Equipos |
| Equipos contra los que se juega | **Rivales** | Equipos |
| Estados del enfrentamiento | Borrador · Convocado · Alineado · Jugado · Acta cerrada | otros sinónimos |
| Pestañas de la ficha del jugador | Resumen · Estadísticas | Perfil, Jugador |

Formatos comunes:

- **Puntos SNP**: filtro `snp_points` (`{% load zyra_format %}`), entero con separador de miles y «Sin SNP» si no hay dato.
- **Fechas**: `D j M Y` (p. ej. «mié 15 oct 2026»); `j M` solo en listas muy compactas. Las horas, `H:i`.
- **Paginación**: siempre `includes/pagination.html`; no se pagina hasta 30 elementos (jugadores, rivales).
- **Temporada por defecto**: `core/season_choice.choose_season` (temporada actual, «Todas» a un toque y se recuerda la última elección en la sesión).
- **Botones**: verbo en infinitivo y una sola acción primaria por pantalla («Siguiente: …»).
- **Mensajes**: éxito como aviso breve («Resultado del partido 2 guardado.»), error como ventana; nunca «Error» a secas, siempre qué falló y cómo arreglarlo.
- **Tono**: tuteo, frases cortas, sin tecnicismos ni siglas sin explicar.
- **Traducciones**: el msgid es el texto en español; el inglés va en `locale/en/LC_MESSAGES/*.po`.
