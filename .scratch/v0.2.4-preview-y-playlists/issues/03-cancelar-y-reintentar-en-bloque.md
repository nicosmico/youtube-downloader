# 03: Cancelar y reintentar una playlist; reintentar varias descargas con error

**What to build:** Desde el listado, cancelar o reintentar una playlist entera, y elegir varias descargas con error para reintentarlas juntas. Backend en `backend/app/jobs/` y frontend en `frontend/src/app/downloads/` y `core/jobs.service.ts`.

**Blocked by:** None.

**Status:** ready-for-agent

## Backend

Reutilizar `JobQueue.cancel` y `JobQueue.retry` (`backend/app/jobs/queue.py`) y sus reglas; no duplicar la lógica de estados.

- `POST /api/batches/{id}/cancel`: cancela todos los jobs `queued` y en curso de la Batch. Primero los `queued` (que no deben llegar a arrancar mientras se cancelan los activos: hacerlo bajo el lock de la Queue, o con una operación atómica del repositorio como `delete_terminal_of_batch`), después los activos (pueden cancelarse en paralelo o en serie; el tiempo de gracia es por job). Devuelve `{"jobs": [...]}` con los que quedaron `canceled`. 404 `unknown_batch` si no existe. Una Batch sin nada que cancelar devuelve la lista vacía (200).
- `POST /api/batches/{id}/retry`: reintenta todos los `failed`, `canceled` e `interrupted` de la Batch (orden de `playlist_index`). Devuelve `{"jobs": [...]}` en `queued`. 404 si no existe.
- `POST /api/jobs/retry` con `{"ids": [...]}` (máx. 500, sin repetidos): reintenta los que se puedan; los que no existan o no sean reintentables se ignoran. Devuelve `{"jobs": [...]}` con los reintentados. Con `require_engine_ready` igual que el retry individual, si lo tiene.
- Mismos eventos SSE que las operaciones individuales (`job.updated` por job y `queue.updated` una vez al final si es fácil; si no, por job como hoy).
- Rutas en `history_api.py` (ya tiene `/batches/{id}`) o en `api.py`, lo que quede más claro. Cuidado: `POST /api/jobs/retry` no debe chocar con `POST /api/jobs/{job_id}/retry`.
- Tests en `backend/tests/` (p. ej. un `test_bulk_actions.py`), con los fakes de `test_cancel_retry.py`/`test_history_cleanup.py`.

## Frontend

### Menú de la playlist (`downloads.html`, menú `batch-menu`, ~línea 96)

- Añadir "Cancelar descargas" cuando la playlist tiene algún job `queued` o en curso, y "Reintentar fallidas" cuando tiene alguno `failed`, `canceled` o `interrupted`. "Quitar del historial" se queda. El botón del menú hoy se desactiva con `!canRemoveBatch(item)`: debe activarse si hay cualquier acción.
- "Cancelar descargas" pide confirmación con `ui/confirm-dialog.ts` (como "Quitar del historial"): "¿Cancelar las N descargas pendientes de esta playlist?" o similar. "Reintentar fallidas" no pide confirmación.
- La visibilidad se decide con los jobs que el listado tiene de esa Batch (el servidor actúa sobre la Batch entera, así que basta con que el listado sepa que hay al menos uno).

### Filtro "Con error"

- Con ese filtro activo, cada fila tiene una casilla y arriba de la lista hay una barra con "Seleccionar todas" (las cargadas en el filtro) y el botón "Reintentar (N)", desactivado con 0.
- Al reintentar, los jobs pasan a `queued` y salen del filtro por SSE; la selección se vacía. Si falla, se muestra el error con el mecanismo que ya usa el listado.
- La selección solo existe en ese filtro; al cambiar de filtro se vacía.
- Las filas que pertenecen a una playlist también se pueden seleccionar (el filtro "Con error" muestra los jobs; comprueba cómo se agrupan ahí las playlists y decide lo más simple y coherente: casilla por job).

### `jobs.service.ts`

- Métodos `cancelBatch(id)`, `retryBatch(id)`, `retryMany(ids)`. El estado llega por SSE como en las operaciones individuales.

## Acceptance criteria

- [ ] Los tres endpoints con tests (incluido: cancelar una Batch con jobs en cola y en curso, y que ningún `queued` arranque mientras tanto; 404; ids no reintentables ignorados).
- [ ] Menú de la playlist con las dos acciones nuevas, confirmación para cancelar, y tests en `downloads.spec.ts`.
- [ ] Selección y "Reintentar (N)" en "Con error", con tests.
- [ ] `npm run test:ci` y `npm run build`; `docker compose run --rm tests`, `ruff check .`, `ruff format --check .`.
- [ ] Sin textos que expliquen la UI.

## Comments
