# 06 · Roadmap de mejoras

Sin fechas exactas: el esfuerzo es orientativo (XS < 2 h · S ≤ 1 día · M 2-4 días · L 1-2
semanas). Cada mejora agrupa hallazgos de [01-ux-findings.md](01-ux-findings.md).

## Fase 1 · Dos semanas: quick wins y base común

Objetivo: quitar fricción del flujo semanal sin cambiar la estructura, y dejar preparado el
cálculo de fase que necesitan las fases siguientes.

| # | Mejora | Problema que resuelve | Beneficio | Esfuerzo | Dependencias | Riesgos | Criterios de aceptación | Validación |
|---|---|---|---|---|---|---|---|---|
| Q1 | Quitar el cambio de email de «Miembros» | H-23 | Sin vía de cambio de email sin contraseña | XS | — | Ninguno | `update_member` ya no cambia el email; enlace a «Mi perfil»; test | Test automatizado |
| Q2 | Feedback uniforme tras guardar | H-08 | El usuario sabe que funcionó | S | — | Mensajes largos: máx. 1 línea | Todas las vistas POST del flujo emiten un toast con el objeto; test por vista | Revisión + test |
| Q3 | Resultados: volver a `#partido-n` + mensaje | H-04 (mínimo) | Menos búsqueda tras guardar | XS | Q2 | — | Tras guardar, la página se abre en el partido guardado con mensaje | Prueba manual móvil |
| Q4 | Textos de estado y botón de convocatoria | H-09, H-10 | Sin mensajes contradictorios; sin error tardío | S | — | — | Texto vacío según estado; botón primario deshabilitado < 10 con «Faltan N»; aviso de email | Prueba con 3 y 10 convocados |
| Q5 | Resumen con Victoria/Derrota y título con equipos | H-21 | Lectura inmediata | XS | — | — | Etiqueta igual que en el listado; título con equipos | Test de 5 s |
| Q6 | Barra inferior con texto y mismo orden | H-13 | Un solo mapa mental | S | Decisión de etiquetas (Q-IA) | Texto largo en 320 px: abreviar | Mismo orden en escritorio y móvil; etiquetas visibles; `aria-current` en escritorio | Captura a 320/390/768 |
| Q7 | Accesibilidad: `scroll-padding` y objetivos ≥ 24 px | H-27, H-28 | Foco visible; toques acertados | XS | — | — | Foco nunca bajo las barras; lápiz de fecha ≥ 24×24 | Recorrido con Tab en móvil |
| Q8 | Temporada por defecto común | H-17 | Cifras coherentes entre pantallas | XS | — | Cambia lo que ven hoy en Estadísticas | Todas abren en la temporada actual; «Todas» a un toque | Revisión |
| Q9 | Formatos de SNP y fechas | H-18 | Comparables | S | — | Traducción del separador en inglés | Un filtro de plantilla; mismo formato en las 5 pantallas | Capturas |
| Q10 | Nombres sin truncar | H-20 | Sin ambigüedad | S | — | Alturas de chip variables | `short_name` en chips; 2 líneas; plantilla a 3 columnas | Capturas a 390 y 1280 |
| Q11 | Inicio: excluir actas cerradas de «Próximo partido»; plegar Primeros pasos | H-36, H-22 | El próximo partido se ve y es correcto | S | — | — | Pasos hechos plegados; próximo partido sin actas cerradas | Captura móvil |
| Q12 | Función única de fase del enfrentamiento | Base de H-02, H-03, A1, A2 | Una sola regla de estado | S | — | Debe cubrir amistosos y actas reabiertas | Función en `match/` con tests por fase | Tests |

**Decisión previa (Q-IA)**: término del nivel superior (Enfrentamiento o Partido, H-01). Puede
tomarse con la prueba T6 en 2-3 capitanes durante la fase 1.

## Fase 2 · Corto plazo: el flujo del capitán

| # | Mejora | Problema | Beneficio | Esfuerzo | Dependencias | Riesgos | Criterios de aceptación | Validación |
|---|---|---|---|---|---|---|---|---|
| C1 | Panel «Pendiente» en el inicio | H-02 | Nada se queda a medias | M | Q12 | Ruido si hay muchas filas: máx. 3 + «Ver todo» | Lista los enfrentamientos abiertos con su siguiente acción; pasados en rojo | T2; % actas abiertas > 7 días |
| C2 | Página del partido con fases y botón «Siguiente» | H-03, H-40 | Sin búsqueda de botones | M | Q12, H-01 | Regresión en permisos de miembro | Indicador de 4 fases; un primario; «Más» con secundarias; cierre de acta con resumen | T1, T3 |
| C3 | Resultados en una pantalla | H-04 | De 10 a 1-2 cargas | M | Q3, C2 | Validación parcial | 5 partidos editables; guardado parcial; «Guardar y cerrar acta» | T3 |
| C4 | Vocabulario único | H-01, H-07 (nombres) | Comprensión | M | Q-IA | Traducción y PDF | Ningún texto usa «partido» para el enfrentamiento (o al revés); «Advertencia» único | T6 |
| C5 | Crear enfrentamiento simplificado (+ hora y lugar) | H-11, H-12 | Menos campos, menos errores | M | C4 | Migración de `Match` (hora) | Tipo único; casa/fuera; hora y lugar; errores propios | T1 |
| C6 | Selector de convocatoria informativo + «Repetir la última» | H-29 | Decidir sin salir | S | — | Cálculo de asistencias por jugador | SNP, «Jugó X de Y», advertencias visibles; sin paginar hasta 30 | T1 |
| C7 | Advertencias con motivo y deshacer | H-07, H-35 | Errores corregibles | M | C4 | — | Motivo; borrar desde la pestaña; mensaje; registro estructurado | T8 |
| C8 | Inicio del miembro «Tu próximo partido» | H-06 | Respuesta directa | M | Q12 | Cuentas sin jugador enlazado | Convocado / no; pareja y partido tras alinear | T7 |
| C9 | Alineación móvil por orden de juego | H-31, H-30 | Ver el efecto de cada cambio | M | C4 | — | Lista por partido; explicación plegada; barras sin tapar | T1 (parte de parejas) |
| C10 | Compartir resultado | A7 | Menos copia manual | XS-S | C2 | — | Botón tras cerrar acta con texto de marcador y parejas | Uso del botón |

## Fase 3 · Cambios estructurales

| # | Mejora | Problema | Beneficio | Esfuerzo | Dependencias | Riesgos | Criterios de aceptación | Validación |
|---|---|---|---|---|---|---|---|---|
| S1 | Nueva navegación: Inicio · Enfrentamientos · Plantilla · Estadísticas · Club | H-14, H-38, E2-E3 | Configuración visible y separada | M-L | C4, Q6 | Usuarios actuales acostumbrados: avisar en Novedades | Club con Miembros, Mi equipo, Rivales, SNP; menú de cuenta reducido | T5; árbol de tareas (tree test) |
| S2 | Ficha única de jugador | H-25 | Un sitio por jugador | M | S1 | Enlaces existentes a estadísticas | Ficha con pestañas; Estadísticas › Jugador abre la ficha | T4 |
| S3 | Estadísticas por secciones y sin duplicados | H-15, H-16 | Página manejable en móvil | M | Q8 | Usuarios que leen todo seguido | Índice/pestañas; sin circular; barras por temporada | T4; profundidad de scroll |
| S4 | Alta de club en dos pasos | H-33, F5 | Menos abandono (hipótesis) | M | Embudo medido | Datos de club incompletos | Paso 1 con 6 campos; paso 2 posponible | Embudo en back-office |

## Fase 4 · Requiere investigación antes de construir

| # | Iniciativa | Pregunta abierta | Método |
|---|---|---|---|
| R1 | Disponibilidad de jugadores (H-05, A6) | ¿Los capitanes la quieren dentro? ¿Responden los jugadores sin cuenta? | Hipótesis H2 + prototipo en papel con 3 capitanes y 3 jugadores |
| R2 | Visibilidad de «Peores parejas» (H-26) | ¿Molesta o motiva? | Entrevistas (H7) |
| R3 | Confirmación del acta por el rival o los jugadores | ¿Hay disputas de resultados? | Entrevistas |
| R4 | Uso en tablet | ¿Hay capitanes que lo usan en tablet? | Analítica de `RequestMetric` por agente |

## Orden recomendado

1. **Q1** (seguridad), luego **Q12** (base técnica) y el resto de la fase 1 en paralelo.
2. Decisión **Q-IA** con 2-3 capitanes en la fase 1.
3. Fase 2 en este orden: **C2 + C3 + C10** (cierran el ciclo semanal), **C1**, **C4**, **C5**,
   **C6**, **C7**, **C8**, **C9**.
4. Pruebas con usuarios ([05](05-usability-testing-plan.md)) entre las fases 2 y 3, antes de S1.
5. Fase 3 según resultados; R1 solo si H2 se confirma.

## Visión posterior

Zyra pasa de ser el registro de lo que el capitán ya decidió fuera a ser el sitio donde se decide:
el capitán pregunta disponibilidad, convoca con datos, alinea con sugerencia y cierra el acta en
una sola pantalla; el jugador abre la app para saber si juega y con quién, y responde. Los
indicadores para seguirlo son el número de cargas por enfrentamiento cerrado, los días hasta el
cierre del acta y las visitas semanales de miembros.
