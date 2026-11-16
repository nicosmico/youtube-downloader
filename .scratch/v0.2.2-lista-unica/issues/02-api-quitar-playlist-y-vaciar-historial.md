# 02: API para quitar una playlist y vaciar el historial

**What to build:** En el backend:
- `DELETE /api/batches/{batch_id}`: quita los jobs terminales del Batch.
- `DELETE /api/history`: quita todos los jobs terminales.

Las dos son atómicas (`DELETE … AND status IN (terminales) RETURNING id`), borran los Batches que quedan vacíos, responden `{"removed": n}` y, si `n > 0`, publican un único evento SSE `jobs.removed` con `{"ids": [...]}`. Un Batch inexistente da `404 batch_not_found`. No tocan archivos en disco.

Ver la spec, sección "Quitar una playlist y vaciar el historial", parte Backend.

**Blocked by:** None (can start immediately).

**Status:** resolved

- [x] Solo se quitan jobs terminales; los que están en curso se quedan.
- [x] El Batch se borra cuando queda sin jobs; `job_output` se borra en cascada.
- [x] `jobs.removed` se publica una vez con los ids, y nunca con `n = 0`.
- [x] `404 batch_not_found` para un Batch desconocido.
- [x] Los archivos descargados no se tocan.
- [x] Tests de repositorio, cola y API; `ruff check` y `ruff format --check` limpios.

## Comments

### 2026-11-16: implementado (backend)

- `DELETE /api/batches/{batch_id}` -> `200 {"removed": n}` (n puede ser 0); Batch desconocido -> `404 {"code": "batch_not_found", "message": "No se encontró la playlist."}`.
- `DELETE /api/history` -> `200 {"removed": n}`.
- Evento SSE `jobs.removed` con `{"ids": [...]}`, una vez por llamada, solo si `n > 0` (`JobEvents.jobs_removed`). `job.removed` no cambia.
- Código: `JobRepository.delete_terminal_of_batch` / `delete_all_terminal` (una sentencia `DELETE ... WHERE status IN (terminales) RETURNING id, batch_id`; SQLite 3.51 en el contenedor, RETURNING requiere >= 3.35), `JobQueue.remove_batch` / `clear_history` (bajo el lock de la cola, el evento se publica fuera de él), rutas en `backend/app/jobs/history_api.py` (router nuevo, montado en `main.py` bajo `/api`).
- Decisiones: los Batches que se borran son solo los que acaban de perder algún job y quedaron vacíos (no un barrido de todos los vacíos), para no borrar un Batch que `enqueue_batch` acaba de crear y aún no ha llenado. No se publica `queue.updated`: sus contadores solo cuentan jobs `queued` y activos, que estas operaciones nunca tocan. `job_output` cae por `ON DELETE CASCADE` (la conexión tiene `foreign_keys=ON`; hay test).
- Sin desviaciones de la spec. No se añadió término al GLOSSARY.
- Verificado: `docker compose run --rm tests` (715 passed, 3 deselected; 18 tests nuevos en `backend/tests/test_history_cleanup.py`: repositorio, API, evento, cascada, archivos intactos, 404, cabecera de la app obligatoria -> 403), `ruff check .` y `ruff format --check .` limpios.

**2026-11-16 — Resuelto.** Publicado en `v0.2.2` (Native/Release `43963527519`; en main, CI `43963250355` y Native `43963250353`). Revisión del orquestador contra el backend real: playlist de prueba, filtros, quitar playlist, vaciar historial (archivos intactos), arranque sin aviso rojo, claro, oscuro y 320 px. Corrección añadida en la integración: la confirmación de cancelar desaparece si la descarga termina mientras tanto.
