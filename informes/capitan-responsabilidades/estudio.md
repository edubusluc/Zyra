# Estudio: ¿entiende el capitán lo que tiene que hacer? (17/10/2026)

**Conclusión:** antes no era suficientemente claro. Ahora se dice en los tres puntos del recorrido y se explica el traspaso.

## Antes (evidencia)

| Punto | Texto | Problema |
|---|---|---|
| Tarjeta «Registrarme como capitán» (`register_choose.html`) | «Crea el club de tu equipo, convoca a tus jugadores y apunta los resultados.» | Habla de crear el club, pero no de invitar ni de crear equipos, ni de que los demás solo consultan. Sin aviso de traspaso (la tarjeta de jugador sí tenía nota). |
| «Registrar un club» (`register_club.html`) | «Cada club gestiona sus propios jugadores…» | Describe privacidad, no responsabilidades. «Tu jugador» solo dice «Como capitán también juegas». |
| «Primeros pasos» (`home.html`) | Tareas sueltas: conectar SNP, invitar, crear enfrentamiento | Nunca dice que todo recae en el capitán ni que se puede ceder. |
| «Miembros» (`club_members.html`) | «Un club tiene un solo capitán. Para traspasar…» | Es el único sitio del traspaso y está en letra pequeña, tras el alta. |

## Cómo funciona el traspaso hoy

- Botón «Hacer capitán» en Club › Miembros (`transfer_captaincy_view` → `services.transfer_captaincy`).
- Solo un capitán por club; el nuevo capitán debe ser otro miembro enlazado a un jugador del club.
- El anterior pasa a miembro (solo lectura). Se borran las credenciales SNP (eran del capitán saliente) y el nuevo capitán vuelve a ver «Primeros pasos».
- Un capitán no puede abandonar el club ni borrar su cuenta sin traspasar antes.

## Cambios

- Tarjeta de elección: nota con las tareas y el traspaso.
- «Registrar un club»: aviso con las tres tareas (invitar, crear equipos/enfrentamientos/convocatorias, apuntar resultados) y el traspaso desde Club › Miembros.
- «Primeros pasos»: línea bajo el título con enlace a «Miembros».
- «Miembros»: nota que explica «Hacer capitán» y sus efectos.
- es/en actualizados; test en `core/tests_account_without_club.py`.
