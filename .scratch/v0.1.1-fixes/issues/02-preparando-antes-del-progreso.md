# 02: "Preparando…" antes del progreso

**What to build:** Mientras un job está `downloading` y todavía no recibió bytes (fase en la que `yt-dlp` consulta a YouTube y resuelve el reproductor con Deno), su tarjeta muestra "Preparando…" sin barra de progreso, en vez de "Descargando 0 %". En cuanto llega la primera línea de progreso, pasa a "Descargando" con porcentaje, bytes, velocidad y tiempo restante. Solo cambia la UI.

**Blocked by:** None (can start immediately).

**Status:** ready-for-agent

- [x] Un job `downloading` sin `downloadedBytes` se muestra como "Preparando…".
- [x] Con la primera actualización de progreso pasa a "Descargando" con sus datos.
- [x] Un reintento vuelve a mostrar "Preparando…" hasta su primer progreso.
- [x] Tests de componente para ambos estados y la transición.

## Comments

**2026-11-15**: implementado en la rama `ticket/v011-app` (sin push).

- `Downloads.isPreparing(job)`: `downloading` con `downloadedBytes === null` muestra "Preparando…" y oculta barra y cifras (la cancelación sigue disponible). El primer progreso lo pasa a "Descargando". El reintento ya limpia `downloaded_bytes` en el backend, así que vuelve a "Preparando…" sin cambios allí.
- Verificado: tests de componente (estado, transición y reintento) y una descarga real en Docker, observada con un `MutationObserver`: `Preparando…` → `Descargando` (con barra) → `Completada`.
