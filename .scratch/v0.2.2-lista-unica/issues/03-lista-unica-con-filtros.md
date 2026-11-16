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

**Status:** resolved

- [x] Una sola lista; un job que termina no cambia de posición.
- [x] Los filtros muestran los estados de la tabla de la spec, "En curso" con contador, y nunca quedan vacíos por paginación.
- [x] Las cabeceras por día son correctas (Hoy, Ayer, fecha corta, año solo si no es el actual) y la playlist aparece en su día.
- [x] Al encolar con un filtro que la oculta, se vuelve a "Todas".
- [x] "Quitar del historial" del Batch y "Vaciar historial", con confirmación accesible (foco, `Esc`, foco de vuelta).
- [x] `jobs.removed` actualiza la lista.
- [x] Contraste AA y foco visible en claro y oscuro; filtros sin desbordar a 320 px.
- [x] Tests de componente y de servicio.

## Comments

### 2026-11-16 (agente)

**Construido** (solo `frontend/`, sin tocar `backend/` ni `preview/`):
- `JobsService`: `jobs` sigue siendo la lista de todo lo conocido; nuevo `filter` + `select()`, `visibleJobs`, `hasMore`, `loading`, `loadingMore`, `loadMore()` por filtro. Cada filtro terminal (`completed`, `failed` = `failed,interrupted`, `canceled`) y "Todas" (historial `completed,failed,canceled,interrupted`) tienen su propia paginación: cursor, "suelo" (`createdAt` del job más viejo al que llegan sus páginas) y estado de carga. "En curso" no pagina (la cola se carga entera, límite 200). "Todas" = en curso (siempre) + terminales hasta su suelo, así un filtro nunca enseña huecos ni queda vacío porque sus jobs estén en una página de otro. `refresh()` (cada reconexión) vuelve a pedir la cola y la primera página del filtro actual; los demás filtros quedan sin cargar y piden su primera página al seleccionarse. Las respuestas de una lista anterior (época) se ignoran. Si se quita el job al que apunta un cursor, el cursor pasa al más viejo que queda (si no, "Cargar más" terminaba sin avisar).
- Nuevos `removeBatch()` (`DELETE /api/batches/{id}`), `clearHistory()` (`DELETE /api/history`) y SSE `jobs.removed`; en error, el mismo patrón que `remove()` (refresca y lanza `EnqueueError`; el componente muestra `action-message`).
- `Downloads`: sin pestañas; fila de chips (`role=group`, `aria-pressed`, `overflow-x-auto`, sin wrap; `En curso · N` con N = `active + queued`), menú ⋮ al final de la fila con "Vaciar historial" (fuera del scroller para que el menú no se recorte). Cabeceras `<h3>` por día local (Hoy, Ayer, "12 nov", "12 nov 2025" si no es este año; meses en `TEXTS`, sin depender de ICU). El reloj es inyectable (`NOW` en `core/clock.ts`). Un Batch es una tarjeta bajo el día de su job más reciente. Estados vacíos por filtro (sin texto de ayuda; no se muestran mientras llega la primera página). Si entra un job en cola con un filtro distinto de "En curso", se vuelve a "Todas" (también para reintentos y jobs de otra pestaña, como antes con la pestaña activa).
- Batch: ⋮ con "Quitar del historial". Nuevo `ui/confirm-dialog.ts` (`<dialog>` nativo con `showModal`; foco inicial en "Cancelar"; Esc, botón o clic fuera cancelan; evento `closed` para devolver el foco). El foco vuelve al ⋮ de origen; si la tarjeta del Batch desaparece, al chip de filtro activo.
- Tests: `downloads.spec.ts` (viejos tests de pestañas reescritos; nuevos bloques de filtros, días, Batch bajo su día, diálogos de Batch e historial con confirmar/cancelar/Esc/clic fuera/foco/HTTP/error, `jobs.removed`, vacíos), `jobs.service.spec.ts` (filtros, consultas y cursores, "nunca vacío", suelo, reconexión, época, cursor eliminado, `removeBatch`, `clearHistory`, `jobs.removed`), y `testing/dialog.ts` (polyfill del `<dialog>` para jsdom) y helpers `jobAt`/`localIso` en `fixtures.ts`.

**Decisiones y desviaciones**
- El ⋮ del Batch se deshabilita entero cuando no hay jobs terminales (en vez de abrir un menú con un único elemento deshabilitado).
- Título del diálogo en singular con N = 1: "¿Quitar 1 descarga del historial?" (la spec solo da el plural).
- N cuenta todos los jobs terminales del Batch que conoce el cliente, aunque el filtro activo oculte algunos.
- Un job viejo en curso que fuera del rango cargado de "Todas" termina deja de verse (queda en su página no cargada); es consecuencia de no mostrar huecos.
- Al cambiar de filtro tras haber paginado "Todas", "Cargar más" del nuevo filtro puede traer jobs que ya se conocían (los cursores son independientes).
- Se eliminaron los textos `queueHeading`, `historyHeading`, `emptyActive`, `emptyHistory`.

**Verificado**: `npm run test:ci` (319 tests, 10 archivos) y `npm run build` pasan. Prueba manual en el navegador contra un servidor falso (no contra el backend real, que hace el ticket 02): lista agrupada por día, diálogo del Batch y del historial, Esc, foco de vuelta, filtro de 320 px sin desbordar la página (los chips hacen scroll) y modo oscuro. El contraste usa los tokens existentes (sin colores nuevos) y el foco visible el `:focus-visible` global.

**2026-11-16 — Resuelto.** Publicado en `v0.2.2` (Native/Release `43963527519`; en main, CI `43963250355` y Native `43963250353`). Revisión del orquestador contra el backend real: playlist de prueba, filtros, quitar playlist, vaciar historial (archivos intactos), arranque sin aviso rojo, claro, oscuro y 320 px. Corrección añadida en la integración: la confirmación de cancelar desaparece si la descarga termina mientras tanto.
