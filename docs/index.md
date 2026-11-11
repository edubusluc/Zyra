# Zyra

Zyra es la aplicación web para gestionar equipos de pádel: jugadores, convocatorias, partidos,
informes PDF por email y estadísticas. Está hecha con Django y funciona en español e inglés.

Esta web se genera sola desde el repositorio en cada subida a `main`, así que siempre describe
el código que hay en producción.

<div class="z-cards" markdown>
<a href="funcionalidades/"><strong>Funcionalidades</strong><span>Qué hace la web, pantalla a pantalla y por rol.</span></a>
<a href="novedades/"><strong>Novedades</strong><span>Lo que ha entrado en cada pull request.</span></a>
<a href="referencia/"><strong>Referencia del código</strong><span>Cada módulo, clase y función con su documentación.</span></a>
<a href="mantener-documentacion/"><strong>Mantener la documentación</strong><span>Qué hacer en cada cambio para que esto siga al día.</span></a>
</div>

## Cómo está organizado el código

| Aplicación | Qué contiene |
|---|---|
| `core` | Clubes, miembros y roles (capitán / miembro), invitaciones, registro y Google, emails, fotos, identificadores públicos, permisos. |
| `players` | Jugadores, enlace jugador ↔ cuenta, cuenta SNP cifrada, puntos SNP y «Completar equipo» desde SNP. |
| `team` | Equipos del club y rivales (categoría, país, división), edición de varios a la vez. |
| `match` | Partidos, convocatorias, parejas y resultados, cierre de actas, informe PDF y su envío. |
| `call`, `callLog`, `penalty` | Modelo de convocatoria, disponibilidad y advertencias. |
| `data_analyse` | Estadísticas de equipo, jugador, parejas y avisos. |
| `backoffice` | Panel del dueño de la plataforma: métricas, clubes, usuarios, procesos programados, consola SQL, importación, fotos. |
| `zyra` | Configuración de Django (ajustes, URLs, WSGI). |

## Puesta en marcha

Las instrucciones para arrancar la app en local, la base de datos y la configuración de
producción están en el [README del repositorio](https://github.com/edubusluc/Zyra#readme).
