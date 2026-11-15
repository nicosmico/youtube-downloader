# 06: Cola persistente y concurrencia

**What to build:** Varios `DownloadJob` conviven en una `Queue` FIFO con un máximo de dos ejecuciones simultáneas. Los estados se persisten: los `queued` se reanudan al reiniciar, y los que estaban `downloading` o `processing` pasan a `interrupted`. La UI muestra varias tarjetas de cola y se actualiza con `queue.updated`.

**Blocked by:** 05 (Descarga de un video end-to-end), 14 (Smoke de empaquetado nativo).

**Status:** ready-for-agent

- [x] Con cinco jobs encolados nunca hay más de dos activos.
- [x] El orden FIFO se respeta.
- [x] Un reinicio conserva `queued`, `completed` y `failed`.
- [x] Los jobs activos al cerrar quedan `interrupted`.
- [x] Los `queued` se reanudan automáticamente tras reiniciar.
- [x] La UI refleja la cola y los estados sin recargar.
- [x] Una actualización del Engine, automática o manual, pausa el despacho, espera a que terminen los jobs activos, intercambia el binario y reanuda la `Queue` (ADR-0002). La manual responde `202` en vez del `409` provisional del ticket 03, y la UI muestra que la actualización está pendiente.
- [x] Tests de concurrencia y persistencia con SQLite temporal.

## Comments

**2026-11-15 — Implementación.**

- **Reconciliación al arrancar** (`JobQueue.start()`): los jobs `downloading`/`processing` pasan a `interrupted` con "La aplicación se cerró durante la descarga." y `finished_at`; `clean_orphans` borra todo el staging antes de despachar; los `queued` se reanudan por FIFO. `completed`/`failed` quedan intactos.
- **Apagado ordenado** (`JobQueue.shutdown`, desde el `lifespan`, así que sirve para el botón y para señales): deja de despachar, hace `terminate()` al árbol de yt-dlp, espera `grace` (3 s), `kill()` y espera `kill_wait` (2 s); el runner marca `interrupted` los jobs cuyo proceso murió por el apagado (`interrupted()` en `JobRunner.run`) y lo que quede sin marcar lo marca el propio apagado. Un proceso que nace después de empezar el apagado se termina en cuanto existe su handle.
- **Pausa por actualización (ADR-0002)**: `EngineManager` recibe tres ganchos (`hold_queue`, `can_update`, `release_queue`) que `create_app` conecta a `JobQueue.hold/is_idle/release`; la cola avisa con `on_drained` cuando el último job activo termina estando retenida. `update_ytdlp`/`start_update` reclaman la actualización, retienen la cola y, si hay jobs activos, dejan `updatePending: true` y devuelven `DEFERRED`; al drenar, `apply_pending_update` ejecuta el intercambio y libera la cola (también si falla). Las actualizaciones automática y manual comparten ese camino.
- **API/SSE**: `POST /api/system/engine/update` responde `202` también con descargas activas (el `409 engine_busy` queda solo para "ya hay una actualización en curso o pendiente"); `EngineInfo` expone `updatePending`; el snapshot inicial del stream incluye ahora `queue.updated`. `queue.updated` se publica bajo el lock de la cola para que el orden sea el de los cambios.
- **UI**: línea "N activas · M en cola" desde `queue.updated`, estado "Interrumpida" y aviso "Actualización pendiente: se aplicará al terminar las descargas en curso." con el botón deshabilitado.
- **Tests**: `backend/tests/test_queue.py` (cinco jobs con puertas del `FakeEngine`, FIFO con `created_at` igual y desordenado, reinicio con SQLite temporal, apagado con handles falsos, pausa manual/automática/fallida), más ajustes en `test_engine_manager.py`/`test_api_engine.py`; Vitest para etiqueta, aviso y cola en vivo.
- **Verificación real** (`docker compose up`, `HOST_DOWNLOAD_DIR=.dev-data/downloads`): tres descargas simultáneas, `GET /api/jobs` nunca mostró más de dos `downloading`; con tres videos largos en cola, `docker compose restart app` dejó los dos activos `interrupted` (staging vacío, sin procesos huérfanos) y el `queued` se reanudó solo. La UI solo se probó con tests de componente.
