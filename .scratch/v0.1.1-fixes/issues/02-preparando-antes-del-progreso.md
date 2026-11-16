# 02: "Preparando…" antes del progreso

**What to build:** Mientras un job está `downloading` y todavía no recibió bytes (fase en la que `yt-dlp` consulta a YouTube y resuelve el reproductor con Deno), su tarjeta muestra "Preparando…" sin barra de progreso, en vez de "Descargando 0 %". En cuanto llega la primera línea de progreso, pasa a "Descargando" con porcentaje, bytes, velocidad y tiempo restante. Solo cambia la UI.

**Blocked by:** None (can start immediately).

**Status:** ready-for-agent

- [ ] Un job `downloading` sin `downloadedBytes` se muestra como "Preparando…".
- [ ] Con la primera actualización de progreso pasa a "Descargando" con sus datos.
- [ ] Un reintento vuelve a mostrar "Preparando…" hasta su primer progreso.
- [ ] Tests de componente para ambos estados y la transición.
