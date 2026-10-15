# 00 · Resumen ejecutivo · Auditoría UX/UI de Zyra Padel

15/10/2026 · `main` tras el PR #153 · app local con datos de prueba, en escritorio, tablet y móvil.
Sin cambios en la aplicación.

| Documento | Contenido |
|---|---|
| [01 · Hallazgos](01-ux-findings.md) | 40 hallazgos con evidencia, prioridad y recomendación; fortalezas |
| [02 · Arquitectura de información](02-information-architecture.md) | Mapa actual y propuesto, duplicidades, información ausente |
| [03 · Flujos y accesos rápidos](03-user-flows-and-shortcuts.md) | Flujo medido del capitán, flujos optimizados, accesos rápidos, benchmark, wireframes |
| [04 · UI, responsive y accesibilidad](04-ui-responsive-accessibility.md) | Medidas por tamaño, WCAG 2.2 AA automático y manual |
| [05 · Plan de pruebas](05-usability-testing-plan.md) | 9 hipótesis, perfiles, 9 tareas, guion y métricas |
| [06 · Roadmap](06-improvement-roadmap.md) | Fase de 2 semanas, corto plazo, estructurales, investigación |
| [07 · Cobertura](07-audit-coverage.md) | Pantallas, flujos, pruebas y lo que falta |

## Estado general

Zyra es **fácil de aprender pantalla a pantalla** y tiene una base técnica y visual sólida: el
listado de partidos en tarjetas, la alineación sugerida, la validación de resultados en vivo y una
accesibilidad sin incumplimientos automáticos. Ninguna tarea esencial está bloqueada.

Donde falla es en **el conjunto**: el ciclo semanal del capitán está repartido en muchas visitas a
la misma página sin indicación del siguiente paso, el inicio no recuerda lo que quedó a medias, el
vocabulario usa «partido» para dos cosas y el jugador (miembro) no encuentra la única respuesta que
busca: si juega y con quién. Son problemas de **arquitectura de información y de flujo**, no de
estética.

## Principales fortalezas

1. Listado de enfrentamientos en tarjetas con estado en palabras, marcador y lugar.
2. Alineación sugerida con alternativa y explicación.
3. Validación de resultados en vivo con reglas de pádel reales.
4. Confirmaciones fuertes en acciones destructivas (borrar club, quitar miembro, capitanía).
5. 0 incumplimientos de axe-core (WCAG 2.2 AA) en 45 pantallas × 2-3 tamaños; enlace de salto, foco visible, movimiento reducido.
6. Sin desbordamiento horizontal a 320, 390 y 768 px (salvo 1 px en un caso).

## Problemas más importantes

| ID | Problema | Evidencia |
|---|---|---|
| H-01 | «Partido» designa el enfrentamiento y también cada uno de sus 5 partidos | Menú «Partidos» y sección «Partidos» dentro del partido; botón «Crear partidos» |
| H-02 | El inicio no muestra lo pendiente: un enfrentamiento del 4/10 sin convocatoria desaparece y el inicio dice «No hay partidos programados» | Captura y consulta de `core/views.py` |
| H-03 | La página del partido cambia sus botones en cada fase y no dice cuál es el siguiente paso | Flujo completo ejecutado |
| H-04 | Apuntar los 5 resultados son 10 cargas de página; tras cada una se vuelve arriba sin confirmación | Flujo medido |
| H-06 | El miembro no ve si está convocado ni con quién juega | Inicio del miembro |
| H-05 | La disponibilidad se gestiona fuera de la app (hipótesis a validar) | Sin modelo ni pantalla |
| H-23 | En «Miembros» el capitán cambia su email sin contraseña; en «Mi perfil» se exige | Código de `update_member` |

## Fricciones en tareas esenciales

- **Ciclo completo de un enfrentamiento** (crear, convocar 12, cerrar, alinear, 5 resultados,
  cerrar acta): **19 cargas de página y unas 58 interacciones** en la prueba automatizada en móvil;
  31 de ellas son de resultados.
- **Errores que se descubren tarde**: cerrar una convocatoria con menos de 10 se permite y falla
  después; la validación de «Crear partido» usa la burbuja nativa del navegador.
- **Feedback irregular**: crear convocatoria, guardar resultado, aplicar advertencia y cerrar acta no
  confirman nada.
- **Sanciones sin deshacer**: un toque por error deja una advertencia permanente.

## Oportunidades de simplificación más interesantes

1. **Resultados de los 5 partidos en una pantalla** con «Guardar y cerrar acta» (de 10 a 1-2 cargas).
2. **Panel «Pendiente»** en el inicio con la siguiente acción de cada enfrentamiento abierto.
3. **Un botón «Siguiente»** fijo en la página del partido con indicador de fases.
4. **«Repetir la última convocatoria»** y datos para decidir (SNP, asistencia, advertencias) en el selector.
5. **«Jugamos en casa / fuera»** en lugar de elegir local y visitante.
6. **Compartir el resultado** al cerrar el acta.

El flujo optimizado estimado baja de 19 a 8 cargas de página (estimación, no medida).

## Diez mejoras prioritarias

| # | Mejora | Hallazgos | Esfuerzo |
|---|---|---|---|
| 1 | Página del partido con fases y botón «Siguiente» | H-03, H-09, H-10, H-40 | M |
| 2 | Resultados en una pantalla (y, ya, volver al partido guardado con mensaje) | H-04 | XS + M |
| 3 | Panel «Pendiente» en el inicio del capitán | H-02, H-22, H-36 | M |
| 4 | Vocabulario único (Enfrentamiento / Partido 1-5; Advertencia) | H-01, H-07 | M |
| 5 | Feedback uniforme tras cada acción | H-08 | S |
| 6 | «Tu próximo partido» en el inicio del miembro | H-06 | M |
| 7 | Navegación móvil con texto, mismo orden, y sección Club | H-13, H-14 | S + M |
| 8 | Selector de convocatoria con datos y «Repetir la última»; nombres sin truncar | H-29, H-20 | S |
| 9 | Crear enfrentamiento simplificado con hora y lugar | H-11, H-12 | M |
| 10 | Quitar el cambio de email sin contraseña en «Miembros» | H-23 | XS |

## Decisiones estructurales a replantear

1. **Navegación**: Inicio · Enfrentamientos · Plantilla · Estadísticas · **Club** (Miembros,
   Mi equipo, Rivales, Cuenta SNP). «Equipos» deja de estar en la navegación principal y el menú
   de cuenta queda solo para la cuenta ([02](02-information-architecture.md)).
2. **El inicio como panel de trabajo**, distinto para capitán (pendiente) y miembro (tu partido).
3. **El enfrentamiento como asistente por fases**, no como página con botones que aparecen.
4. **Una ficha por jugador** que reúna datos y estadísticas.
5. **El papel del miembro**: de solo lectura a responder disponibilidad (si se valida).

## Hipótesis que requieren validación con usuarios

H1 confusión de términos · H2 disponibilidad fuera de la app · H3 resultados de una vez desde el
móvil · H4 lo pendiente no se encuentra · H5 los jugadores entran para saber si juegan · H6
invitar no es descubrible · H7 «Peores parejas» incomoda · H8 solo se lee la parte alta de las
estadísticas · H9 dudas en el alta de club. Plan en [05](05-usability-testing-plan.md).

## Orden recomendado

1. Fase 1 (2 semanas): quick wins Q1-Q11 y la función común de fase del enfrentamiento (Q12);
   decidir el término con 2-3 capitanes.
2. Fase 2: página del partido por fases + resultados en una pantalla + compartir; después panel
   «Pendiente», vocabulario, crear simplificado, convocatoria, advertencias, inicio del miembro.
3. Pruebas con 5-8 usuarios.
4. Fase 3: nueva navegación con Club, ficha única, estadísticas por secciones, alta en dos pasos.
5. Disponibilidad solo si se confirma H2.

## Riesgos y limitaciones

- **No se pudo abrir https://zyrapadel.com/** (el proxy del entorno devolvió 403): todo se observó
  en local con `main` y datos de prueba.
- **No hay datos de uso ni pruebas con usuarios**: frecuencias e impactos son estimaciones; las
  hipótesis están marcadas como tales.
- **Sin lector de pantalla real ni zoom al 200 %**; la accesibilidad automática no equivale a
  conformidad.
- No recorridos: back-office, importación SNP, aceptar invitación, Google, PDF y correos, interfaz
  en inglés (detalle en [07](07-audit-coverage.md)).

## Confianza de las conclusiones

- **Alta** en los problemas de flujo, feedback, estados, terminología y responsive: observados y
  medidos en el navegador (C1).
- **Media** en los de código no ejecutado (H-23, H-07 sin deshacer): inspección de plantillas y vistas (C2).
- **Baja-media** en el valor de disponibilidad, el inicio del miembro, «Peores parejas» y el alta:
  dependen de usuarios (C3).
- No se da una puntuación global de usabilidad: no hay una metodología válida sin participantes.
