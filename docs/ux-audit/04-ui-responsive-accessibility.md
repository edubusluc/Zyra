# 04 · UI, responsive y accesibilidad

Mediciones del 15/10/2026 con Chromium (Playwright) a 1280×800 (escritorio), 768×1024 (tablet),
390×844 (móvil) y 320×640 (móvil pequeño). Detalle de cada hallazgo en
[01-ux-findings.md](01-ux-findings.md); aquí se agrupan por tema con la evidencia visual.

## 1. UI y jerarquía visual

### Lo que está bien

- Sistema visual consistente: fondo oscuro, lima como único color de acento, tipografía de
  titulares propia y tarjetas con el mismo radio y borde.
- Un único botón primario lima por pantalla en la mayoría de formularios.
- Estados de tarjeta de partido con color **y** palabra (Victoria, Derrota, Sin resultado): no
  depende solo del color ([captura](capturas/escritorio-partidos.jpg)).

### Problemas que afectan a la comprensión o a la tarea

| Elemento | Problema | Propuesta | Beneficio | Hallazgo |
|---|---|---|---|---|
| Botón «Cerrar convocatoria» | Rojo (`btn-danger`) para avanzar | Primario; rojo solo para borrar | El color vuelve a significar peligro | H-10 |
| Fila de acciones del partido | Hasta 5 botones secundarios del mismo peso | Un primario «Siguiente» + menú «Más» | Se ve qué hacer | H-03 |
| Insignias de estado | «Sin validar», «Abierta», «Cerrada», «Acta cerrada», «Pdt. cerrar acta» | Un vocabulario de fases | Un solo modelo mental | H-03 |
| Marcador del resumen | «5/7» sin palabra | «5 – 7 · DERROTA» | Lectura en 1 s | H-21 |
| Estadísticas | Balance ×3, gráfico circular y línea suavizada | Cifra + barras por temporada | Menos ruido, gráfico fiel | H-16 |
| Nombres de jugador | Truncados a una línea | `short_name`, dos líneas | Sin ambigüedad | H-20 |
| Primeros pasos | 5 filas con 4 tachadas | Una línea «4 de 5» | El próximo partido sube | H-22 |
| Formatos | SNP con coma, punto, espacio o «-»; dos formatos de fecha | Un filtro común | Comparar cifras | H-18 |
| Paginación | 4 estilos | Un componente | Previsibilidad | H-19 |
| Títulos y etiquetas | Mayúsculas y «:» sin criterio | Guía de estilo | Pulido | H-39 |

### Preferencias estéticas (no son problemas)

- El uso intensivo de mayúsculas y cursiva en titulares es parte de la marca; solo se recomienda
  revisar la legibilidad de párrafos en mayúsculas (no los hay en contenido largo).
- El fondo degradado no afecta al contraste medido (axe con fondo sólido de peor caso).

## 2. Responsive

### Medidas por pantalla (alto total en px; sin desbordamiento horizontal salvo donde se indica)

| Pantalla | Escritorio | Tablet 768 | Móvil 390 | Móvil 320 |
|---|---|---|---|---|
| Inicio (capitán) | 1.420 | 1.537 | 1.894 | — |
| Partidos | 800 | 1.024 | 1.111 | 1.582 |
| Resumen del partido (acta cerrada) | 1.809 | 2.015 | 2.476 | 3.025 |
| Crear convocatoria | 907 | 1.144 | 2.239 | 2.357 (+1 px de ancho) |
| Gestionar plantilla | 1.193 | 1.556 | 3.134 | — |
| Gestionar equipos | 1.697 | 2.466 | 3.514 | 3.719 |
| Estadísticas de equipo | 5.100 | 6.981 | 8.920 | 10.307 |
| Estadísticas de un jugador | 4.070 | — | 6.115 | — |
| Miembros | 1.038 | 1.143 | 1.514 | 1.685 |

Tabla completa de las 23 pantallas en [07-audit-coverage.md](07-audit-coverage.md).

### Diferencias entre escritorio y móvil

| Aspecto | Escritorio | Móvil | Problema | Hallazgo |
|---|---|---|---|---|
| Navegación | Barra superior con texto | Barra inferior solo iconos, otro orden | Aprender dos mapas | H-13 |
| Tablet (768-991 px) | — | Usa la barra de móvil sin texto | Desaprovecha espacio | H-13 |
| Acciones fijas | No hay | Barra de selección + barra de navegación | A 320 px tapan ~40 % | H-30 |
| Alineación | Orden de juego en columna lateral | Orden al final, tras 1.900 px | No se ve el efecto de cada cambio | H-31 |
| Chips de convocados | Nombre completo | Truncado | Ambigüedad | H-20 |
| Inicio | Próximo partido visible a 900 px | Bajo el pliegue | Lo importante no se ve | H-22 |

Capturas: [inicio móvil](capturas/movil-inicio-capitan.jpg) ·
[jugadores móvil](capturas/movil-jugadores.jpg) · [equipos móvil](capturas/movil-equipos.jpg) ·
[alineación](capturas/movil-alineacion-sugerida.jpg) · [320 px](capturas/movil-320-crear-convocatoria.jpg) ·
[tablet](capturas/tablet-inicio.jpg).

### Formularios en móvil

- Las casillas de resultado usan `inputmode="numeric"`: el teclado numérico aparece (C2).
- Los desplegables propios (`static/js/custom-select.js`) sustituyen al nativo: en móvil se pierde
  la rueda del sistema, pero hay búsqueda; no se observaron problemas de uso.
- La validación de «Crear partido» depende de la burbuja nativa y queda mal colocada (H-12,
  [captura](capturas/movil-crear-partido-validacion.jpg)).
- Selector de archivo nativo sin estilo (H-34, [captura](capturas/movil-editar-mi-jugador.jpg)).

## 3. Accesibilidad (WCAG 2.2 AA)

### Pruebas automáticas

- **Herramienta**: axe-core 4.10.2 inyectado con Playwright; etiquetas `wcag2a`, `wcag2aa`,
  `wcag21aa`, `wcag22aa` y `best-practice`. Contraste medido pintando el fondo con su color más
  claro (como hace `scripts/auditoria_accesibilidad.py`).
- **Resultado**: 0 incumplimientos en 23 pantallas de capitán × 3 tamaños, 11 de miembro × 2,
  8 públicas × 2 y 3 sin club × 2. También `scripts/auditoria_accesibilidad.py` del repositorio:
  0 reglas incumplidas en 32 páginas (escritorio y móvil).
- **Límite**: axe no evalúa la mayoría de criterios de teclado, comprensión, foco oculto ni
  tamaño de objetivo con espaciado. No equivale a conformidad.

### Pruebas manuales realizadas

| Criterio | Prueba | Resultado | Hallazgo |
|---|---|---|---|
| 2.4.1 Saltar bloques | Primer Tab en 4 páginas | «Saltar al contenido» visible | OK |
| 2.4.3 Orden del foco | 40 Tab en Partidos y Resumen (escritorio y móvil) | Orden lógico: salto, marca, navegación, idioma, cuenta, contenido | OK |
| 2.4.7 Foco visible | Estilo calculado de cada elemento enfocado | Contorno o sombra lima en todos; tarjeta de partido con `:focus-within` | OK |
| 2.4.11 Foco no oculto (mínimo) | Posición del foco frente a barras fijas en móvil | Parcialmente tapado por la barra inferior | H-27 |
| 2.5.8 Tamaño del objetivo | Medida de cada elemento interactivo visible | Lápiz de fecha 13×14 px; enlaces de 19-20 px de alto | H-28 |
| 1.3.1 Información y relaciones | Revisión de plantillas | Advertencias solo en `title` | H-29 |
| 3.3.1 / 3.3.3 Identificación y sugerencia de errores | Envíos inválidos | Mensajes claros salvo burbuja nativa en Crear partido y error tardío al cerrar convocatoria | H-12, H-10 |
| 3.2.6 Ayuda consistente | Enlaces de contacto y guías | En el pie de todas las páginas | OK |
| 3.3.7 Entrada redundante | Formularios encadenados | Lugar del partido copiado del equipo; el nombre del capitán se pide una vez | OK |
| 3.3.8 Autenticación accesible | Login | Usuario + contraseña con mostrar/ocultar, Google; sin puzzles | OK |
| 2.3.3 / movimiento | CSS | `prefers-reduced-motion` respetado | OK |
| 1.4.10 Reflow | 320 px en 6 pantallas | Sin scroll horizontal (1 px en convocatoria) | H-30 |

### Pendiente de comprobar

- Lector de pantalla real (VoiceOver iOS y TalkBack): anuncios de los desplegables propios, del
  selector de jugadores (`aria-live` del contador) y del calendario propio.
- Zoom al 200 % en escritorio y texto aumentado en el sistema del móvil.
- Contraste de los textos grises sobre el degradado real (axe usa el peor caso sólido).
- Interfaz en inglés.

## 4. Recomendaciones por orden

1. H-27 y H-28: `scroll-padding` y área táctil mínima (XS, CSS).
2. H-10 y H-12: prevención de errores en los dos formularios del flujo principal (S).
3. H-13: barra inferior con texto y mismo orden (S).
4. H-20 y H-18: nombres y formatos (S).
5. H-29: advertencias visibles como texto en el selector (S).
6. H-16 y H-15: limpiar y dividir estadísticas (S + M).
