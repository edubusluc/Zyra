# Zyra · instrucciones para asistentes

- Localiza el área con `grep -n -i "<palabra>" ZYRA_CONTEXT.md` (columna *Claves*, sinónimos es/en): una
  línea te da vistas, lógica, plantillas, JS, datos y tests. Lee el índice entero solo si no encuentras el área.
- Antes de editar, mira en `ZYRA_CONTEXT.md` § Recetas qué hay que tocar siempre según el tipo de cambio.
- Abre `docs/ai/` solo si cambias reglas, modelos o flujos (enlace en la fila). Amplía la búsqueda solo si
  un import o un FK te saca de la fila.
- El código manda sobre cualquier documento; si encuentras una discrepancia, corrígela en el mismo PR.
- Convenciones: `docs/mantener-documentacion.md` (docstrings en español, novedades, accesibilidad).
- JS, plantilla principal, test, regla, modelo o comando nuevo → actualiza `ZYRA_CONTEXT.md` y el `docs/ai/*.md`
  afectado; `python scripts/check_ai_docs.py` (en CI) lo comprueba.
