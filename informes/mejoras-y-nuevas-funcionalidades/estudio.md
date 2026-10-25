# Zyra · mejoras y nuevas funcionalidades (24/10/2026)

Estudio de `main` (tras #182) para decidir qué implementar ahora. **Fuera de alcance: nuevas ligas** (el selector «Competición» sigue bloqueado en SNP). Solo propuesta, sin código.

Para no repetir, se han cruzado `ZYRA_CONTEXT.md`, `docs/funcionalidades.md`, `docs/novedades.md` y los informes previos (UX audit y su estado `08`, nuevas estadísticas E/J/P/C/R, usabilidad, calidad, monetización, capitán). Ya está hecho y **no se propone de nuevo**: navegación con «Club», fases del enfrentamiento, panel «Pendiente», alineación sugerida, estadísticas de sets/clutch/récords/asistencia, ranking SNP, correo de resultado, compartir resultado en texto, informe mensual, back-office con CRM/auditoría/salud, onboarding en 3 pasos.

Esfuerzo: S = un PR pequeño · M = un PR mediano · L = varios PR o decisión externa. Impacto sobre el uso real del capitán y la retención.

## Recomendación: qué hacer primero

1. **N1 Cara a cara por rival + previa del partido** (E1 + C4 del informe de estadísticas, nunca implementado). Los datos ya existen, no hay migración y responde a «¿contra quién jugamos y cómo nos fue?» justo cuando se convoca. S–M.
2. **N2 Recordatorios y calendario (.ics)**. La asistencia es el problema diario del capitán y hoy Zyra no avisa a nadie antes del partido. Correo 48 h antes a convocados y enlace de calendario que se actualiza solo. S–M.
3. **N3 Tarjeta de resultado en imagen + enlace público**. Sustituye al texto de WhatsApp por una imagen con marcador y parejas; es la vía de captación más barata (cada resultado compartido enseña Zyra). S–M.
4. En paralelo, **P1 copias de seguridad programadas y alerta de disco**: en octubre el disco se llenó y las copias solo se hacen al desplegar. S.

Después, validando antes con 2–3 capitanes reales: N4 Disponibilidad, N5 Rol de delegado, N6 Notas privadas.

## A. Mejoras sobre lo que ya existe

| ID | Mejora | Por qué | Impacto | Esfuerzo |
|---|---|---|---|---|
| M1 | **Cerrar los pendientes de UX** (informe `08`): fundir «Modo» y «Tipo» al crear enfrentamiento, «Repetir la última convocatoria», advertencias con motivo y «Deshacer» (C7), `scroll-padding` y objetivos ≥ 24 px (Q7), textos sueltos «partido/enfrentamiento» en estadísticas | Son las deudas que el propio audit dejó abiertas; tocan los flujos más repetidos | Alto | S–M |
| M2 | **SNP sin guardar la contraseña**: importar pegando o subiendo la tabla de SNP (o bookmarklet) como alternativa al scraper con credenciales | El aviso legal de SNP prohíbe ceder la contraseña (§5); un bloqueo de cuentas rompería «Completar equipo» y los puntos. Mantiene el scraper como opción hasta tener respuesta de SNP | Alto (riesgo) | L |
| M3 | **Registro de convocatoria estructurado**: guardar acción + jugador + fecha en vez de texto libre (hoy sin traducir en BD, igual que el motivo de `Penalty`) | Arregla un problema conocido y habilita «bajas de última hora» (C3) y la fiabilidad de asistencia | Medio | M |
| M4 | **Cierre de temporada**: asistente que revisa altas y bajas de la plantilla, archiva y deja la nueva temporada lista (hoy «Completar equipo» lo ejecuta el admin a mano antes de temporada) | Es el momento de más fricción y de más riesgo de abandono; encaja con el resumen de temporada (N8) | Medio-alto | M |
| M5 | **Estadísticas sin el cuello del capitán**: el miembro ve «Mi forma» y su racha en Inicio (J8, parcial hoy) y «Parejas por mejorar» visible (R2) | Dar al jugador una razón para entrar sin que el capitán le avise | Medio | S |
| M6 | **Uso en tablet** (R4 del audit, sin empezar): revisar 768–1024 px en alineación y estadísticas | El capitán usa tablet en el club; es el único ancho sin revisar | Bajo-medio | S |

## B. Plataforma y operación

| ID | Propuesta | Por qué | Impacto | Esfuerzo |
|---|---|---|---|---|
| P1 | **Copias programadas fuera del servidor + alerta de disco** (`deploy/backup.sh` ya existe; solo se lanza al desplegar). Añadir cron, `BACKUP_RSYNC_TARGET`, prueba de restauración y un indicador de disco en «Salud» del back-office | El 21/10 el disco se llenó con imágenes antiguas; una pérdida de datos no tiene vuelta atrás | Alto | S |
| P2 | **Donación y patrocinador local** (etapa 1 de `informe-monetizacion.md`): botón de donación y logo opcional en el PDF/correos | Cubre los ≈125 €/año de servidor sin tocar funciones; pendiente desde el 07/10 | Medio | S |
| P3 | **Exportar a CSV/Excel** (R3): enfrentamientos, resultados y estadísticas de jugador | Petición habitual de capitanes y quita miedo al «lock-in» | Medio | S |

## C. Funcionalidades nuevas

| ID | Funcionalidad | Qué hace | Datos ya disponibles | Impacto | Esfuerzo |
|---|---|---|---|---|---|
| N1 | **Cara a cara por rival + previa del partido** | Lista de rivales con balance, juegos a favor/en contra y último resultado; ficha del rival con historial y nuestras mejores parejas contra él. En el enfrentamiento y la convocatoria, un bloque «Previa» | `Match`, `Game`, `Team` | Alto | S–M |
| N2 | **Recordatorios y calendario** | Correo 48 h antes (y a quien no se ha apuntado), feed `.ics` por club para Google/Apple Calendar y botón «Añadir al calendario» con hora y lugar | `Match.start_date`, hora y lugar (ya existen) | Alto | S–M |
| N3 | **Tarjeta de resultado en imagen + enlace público** | Imagen (PNG) con marcador, parejas y sets para WhatsApp/Instagram; página pública de solo lectura de ese enfrentamiento con `og:image` | Resultado, plantilla de correo | Alto (captación) | S–M |
| N4 | **Disponibilidad de jugadores** | Cada miembro responde «Puedo / No puedo / Duda» a un enfrentamiento; el capitán lo ve en el selector de convocatoria y la convocatoria sigue siendo suya | `Membership`, `Player.user` | Alto, pero hipótesis H-05 sin validar | M |
| N5 | **Rol de delegado** | Segundo rol con permiso para alineaciones y resultados, sin cuenta SNP ni miembros. Cuando el capitán no puede, el club no se para | `Membership.role`, regla de capitán único | Medio-alto | M |
| N6 | **Notas privadas** | Notas del capitán sobre un rival («juegan fuertes al 1 y 2») y sobre un enfrentamiento, visibles en la previa y la convocatoria | — (campo de texto nuevo) | Medio | S |
| N7 | **Crónica automática del enfrentamiento** | Texto en lenguaje natural con el resumen (remontadas, tie-breaks, rachas) listo para pegar en el grupo | `data_analyse.sets`, `records` | Medio | S |
| N8 | **Resumen de temporada («Wrapped»)** | Página al final de temporada: MVP, mejor pareja, mayor racha, quien más sube en SNP, partido más ajustado | Estadísticas existentes | Medio-alto (retención) | M |
| N9 | **Rendimiento frente a su SNP** (J5) y **comparador de jugadores** (J6) | Quién rinde más o menos de lo que dicen sus puntos; dos jugadores lado a lado | `SnpScoreHistory`, `Game` | Medio | M |

## D. Ideas para más adelante (no ahora)

- Cuotas y pagos del equipo con Stripe Connect y plan Pro de 29 €/año (con ~20 clubes ajenos; antes, cuadrar IVA/autónomo).
- Web Push con PWA instalable: solo cuando los recordatorios por correo demuestren uso. En iOS exige instalar la PWA.
- Confirmación del acta por el rival (R3 del audit): requiere que el rival use Zyra.
- Predicción de resultado de una alineación: faltan datos de los jugadores rivales (SNP solo da la clasificación del grupo).

## Orden propuesto

| Fase | Contenido | PR estimados |
|---|---|---|
| 1 (ahora) | N1 + N2 + P1 | 3 |
| 2 | N3 + M1 + P2 | 3 |
| 3 (tras hablar con capitanes) | N4 o N5, N6, M4 | 3 |
| 4 | N8 al acercarse el fin de temporada, M2 según respuesta de SNP | 2–4 |

## Decisiones que necesito de ti

1. ¿Empezamos por la fase 1 completa o solo N1?
2. N4 (disponibilidad): ¿tus capitanes quieren que los jugadores respondan en la app, o ya lo resuelven bien por WhatsApp?
3. N2: ¿el recordatorio sale a todos los convocados o solo a los que no se han apuntado?
