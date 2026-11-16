# 03: Una sola lista de descargas con filtros, días y limpieza

**What to build:** En el frontend (`frontend/src/app/downloads/` y `core/jobs.service.ts`):
- Las pestañas "En curso" e "Historial" se sustituyen por una sola lista ordenada por `createdAt` descendente.
- Filtros como chips: Todas · En curso · N · Completadas · Con error (`failed` + `interrupted`) · Canceladas. Cada filtro terminal tiene su consulta y su cursor de "Cargar más".
- Cabeceras por día: "Hoy", "Ayer", "12 nov".
- Al encolar con un filtro que oculta la descarga, el filtro vuelve a "Todas".
- Menú `⋮` en la tarjeta del Batch con "Quitar del historial", y `⋮` en la fila de filtros con "Vaciar historial". Ambos con un diálogo de confirmación (`<dialog>`) y llamando a `DELETE /api/batches/{id}` y `DELETE /api/history`.
- `JobsService` escucha el evento SSE `jobs.removed` (`{"ids": [...]}`).

El backend de esas rutas lo hace el ticket 02 en paralelo: el contrato está en la spec. Los tests usan `HttpTestingController`.

Ver la spec, secciones "Una sola lista de descargas" y "Quitar una playlist y vaciar el historial", parte Frontend.

**Blocked by:** None (can start immediately; the API contract is fixed in the spec).

**Status:** ready-for-agent

- [ ] Una sola lista; un job que termina no cambia de posición.
- [ ] Los filtros muestran los estados de la tabla de la spec, "En curso" con contador, y nunca quedan vacíos por paginación.
- [ ] Las cabeceras por día son correctas (Hoy, Ayer, fecha corta, año solo si no es el actual) y la playlist aparece en su día.
- [ ] Al encolar con un filtro que la oculta, se vuelve a "Todas".
- [ ] "Quitar del historial" del Batch y "Vaciar historial", con confirmación accesible (foco, `Esc`, foco de vuelta).
- [ ] `jobs.removed` actualiza la lista.
- [ ] Contraste AA y foco visible en claro y oscuro; filtros sin desbordar a 320 px.
- [ ] Tests de componente y de servicio.

## Comments
