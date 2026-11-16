# 04: La tarjeta muestra "En cola" cuando la descarga ya empezó

**What to build:** Que la respuesta HTTP de `POST /api/jobs` y `POST /api/jobs/{id}/retry` nunca sobrescriba un estado más reciente recibido por SSE: solo añade el job si la UI aún no lo conoce. Hoy esa respuesta, con la foto del job antes de despacharlo, llega a veces después del `job.updated` que dice `downloading`, y la tarjeta vuelve a "En cola" hasta el primer progreso. Ver la spec, sección "Fallo En cola".

**Blocked by:** None (can start immediately).

**Status:** ready-for-agent

- [ ] Si el SSE `downloading` llega antes que la respuesta del `POST`, la tarjeta muestra "Preparando…" y no vuelve a "En cola".
- [ ] Si la respuesta llega primero, el job aparece y luego se actualiza con el SSE.
- [ ] Lo mismo para "Reintentar".
- [ ] Tests de servicio que reproducen ambos órdenes de llegada.
