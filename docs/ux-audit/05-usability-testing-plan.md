# 05 · Plan de pruebas con usuarios

Primera iteración cualitativa para validar las hipótesis de esta auditoría. **No se ha hecho
ninguna prueba con usuarios reales**: los tiempos y recuentos de los otros documentos salen de
pruebas automatizadas.

## 1. Objetivos e hipótesis

| ID | Hipótesis | Hallazgos | Cómo se valida |
|---|---|---|---|
| H1 | Los capitanes no distinguen «partido» (enfrentamiento) de «partido 1-5» en la interfaz actual | H-01 | T6: explicar la página del partido |
| H2 | Los capitanes preguntan la disponibilidad fuera de Zyra y pagarían (en tiempo) por tenerla dentro | H-05 | Entrevista + T1 |
| H3 | Tras jugar, el capitán quiere poner los 5 resultados de una vez desde el móvil | H-04 | T3 |
| H4 | Un capitán que vuelve a la app no encuentra lo que dejó a medias | H-02, H-03 | T2 |
| H5 | Los jugadores entran a Zyra sobre todo para saber si juegan y con quién | H-06 | T7 + entrevista |
| H6 | Invitar a alguien nuevo es difícil de encontrar cuando «Primeros pasos» está oculto | H-14 | T5 |
| H7 | «Peores parejas» visible para todos genera incomodidad | H-26 | Entrevista |
| H8 | Las estadísticas de equipo se usan solo en su parte superior | H-15, H-16 | T4 + mapa de scroll |
| H9 | El alta de club con 14 campos provoca dudas (categoría, división, SNP) | H-33 | T9 |

## 2. Participantes (5-8)

| Perfil | Nº | Criterios |
|---|---|---|
| Capitán que ya usa Zyra | 2 | Al menos 4 enfrentamientos cerrados en la app |
| Capitán de SNP que no usa Zyra | 2 | Gestiona su equipo con WhatsApp u hojas de cálculo |
| Jugador miembro con cuenta | 2 | Cuenta enlazada a su jugador |
| Jugador sin cuenta | 1 | Juega en un equipo de SNP |
| (Opcional) persona con tecnología de asistencia | 1 | Usa lector de pantalla o ampliación en el móvil |

Mezclar edades y comodidad con el móvil. Sesiones de 45 min, remotas o presenciales, con el móvil
del participante siempre que sea posible (es el uso real en la pista).

## 3. Preparación

- Entorno de prueba con `python clear_database.py && python populate_db.py` y cuentas
  `capitan` y `jugador` creadas para la sesión; nunca datos reales.
- Estado inicial preparado: un enfrentamiento pasado sin convocatoria (como el del 4/10), uno
  futuro con convocatoria abierta de 8 jugadores y uno cerrado.
- Grabación de pantalla y voz con consentimiento; observador que anota en la hoja de registro.

## 4. Tareas

| ID | Perfil | Escenario | Éxito |
|---|---|---|---|
| T1 | Capitán | «El domingo 25 jugáis fuera contra ICONICO 500 PLUS a las 18:00. Prepara el partido y convoca a estos 12 (lista en papel).» | Partido creado con el equipo propio de visitante y convocatoria cerrada con los 12 |
| T2 | Capitán | «Acabas de abrir Zyra. ¿Tienes algo pendiente? Resuélvelo.» | Identifica el enfrentamiento del 4/10 sin convocatoria en < 60 s |
| T3 | Capitán | «Ya habéis jugado. Estos son los resultados (papel). Apúntalos y cierra el acta.» | Acta cerrada con los 5 resultados correctos |
| T4 | Ambos | «¿Qué pareja ha ganado más esta temporada? ¿Cuántos partidos ha ganado Alberto?» | Respuestas correctas |
| T5 | Capitán | «Un jugador nuevo se une hoy. Invítalo.» | Invitación enviada o enlace copiado |
| T6 | Capitán | Página de un enfrentamiento cerrado, 10 s: «¿Qué es “Partido 3”? ¿Ganasteis?» | Explicación correcta de los dos términos |
| T7 | Jugador | «¿Juegas este domingo? ¿Con quién?» | Respuesta correcta sin ayuda |
| T8 | Capitán | «Alberto no avisó de que no venía. Ponle una advertencia. Ahora quítasela, era un error.» | Advertencia creada; observar qué hace al no poder quitarla |
| T9 | Capitán nuevo | «Registra tu club en Zyra.» | Club creado; anotar dudas por campo |

## 5. Guion del moderador

1. **Bienvenida (3 min)**: «Estamos probando la aplicación, no a ti. Piensa en voz alta. Puedes
   abandonar cualquier tarea.»
2. **Contexto (5 min)**: ¿Cómo organizas hoy una jornada? ¿Qué herramientas usas? ¿Qué es lo más
   pesado? (no mencionar disponibilidad ni nombres de funciones).
3. **Tareas (25-30 min)**: leer el escenario, no dar pistas sobre dónde está nada. Si se bloquea
   2 min, ofrecer una pista y anotarla como «ayuda».
4. **Tras cada tarea**: SEQ («¿Qué tan fácil o difícil ha sido?», 1-7) y confianza («¿Qué
   seguridad tienes de haberlo hecho bien?», 1-5).
5. **Cierre (5 min)**: «Si pudieras cambiar una cosa…», «¿Qué echas de menos?».

### Preguntas de seguimiento

- ¿Qué esperabas que pasara al pulsar este botón?
- ¿Qué significa para ti «convocatoria cerrada»? ¿Y «acta»?
- ¿Cómo le preguntas hoy a tus jugadores si pueden jugar? ¿Cuánto tardan en responder?
- ¿Cuándo pones los resultados? ¿Desde dónde?
- (Jugador) ¿Para qué abrirías Zyra durante la semana?
- ¿Te molestaría que tu nombre saliera en «peores parejas»?

## 6. Métricas

| Métrica | Definición | Umbral de éxito orientativo |
|---|---|---|
| Tasa de finalización | Tareas completadas sin ayuda / intentadas | ≥ 80 % en T1, T3, T7 |
| Tiempo por tarea | Desde leer el escenario hasta terminar | Referencia para la segunda iteración |
| Errores | Acciones que llevan a un estado incorrecto (p. ej. equipo local cambiado) | ≤ 1 por tarea |
| Retrocesos | Uso de «atrás» o vuelta a una pantalla anterior para buscar | Comparar antes/después |
| Solicitudes de ayuda | Pistas del moderador | 0 en T2, T7 |
| Abandono | Tarea dejada sin terminar | 0 en tareas esenciales |
| Confianza percibida | 1-5 tras cada tarea | ≥ 4 |
| SEQ | 1-7 tras cada tarea | ≥ 5,5 |

## 7. Registro de resultados

Hoja con una fila por participante y tarea: participante, perfil, tarea, completada (sí / con
ayuda / no), tiempo, errores, retrocesos, ayudas, SEQ, confianza, citas literales y hallazgo
relacionado (H-xx). Al final de las sesiones: tabla de hipótesis con estado **confirmada /
refutada / sin evidencia** y número de participantes que la apoyan. Guardar las notas en
`docs/ux-audit/` como `08-resultados-pruebas.md` (sin datos personales).

## 8. Criterios para decidir

- **H1 confirmada** (≥ 3 de 4 capitanes confunden los términos) → aplicar H-01 antes que el
  rediseño de la página del partido.
- **H2 confirmada** (≥ 3 de 4 capitanes preguntan fuera y lo consideran pesado) → diseñar la
  disponibilidad (H-05) en la fase 3 del roadmap; si no, aparcarla.
- **H5 refutada** → reducir la inversión en el inicio del miembro a la tarjeta mínima.
