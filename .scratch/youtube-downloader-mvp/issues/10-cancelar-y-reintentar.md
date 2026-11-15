# 10: Cancelar y reintentar

**What to build:** El usuario puede cancelar un job en cola o en curso. La cancelación termina el árbol de procesos sin dejar huérfanos, borra el staging del job y lo deja en `canceled`. Puede reintentar jobs `failed`, `canceled` o `interrupted`, creando un nuevo `Attempt` con staging limpio sin duplicar archivos. En Windows se termina el árbol completo de procesos (Job Object o equivalente).

**Blocked by:** 06 (Cola persistente y concurrencia).

**Status:** ready-for-agent

- [x] Cancelar un job en cola lo saca sin ejecutarlo.
- [x] Cancelar un job activo termina `yt-dlp` y sus hijos (`ffmpeg`, Deno), borra su staging y deja el estado `canceled`.
- [x] No quedan procesos huérfanos tras cancelar.
- [x] Reintentar un job fallido lo reencola con `attempt + 1` y puede completarse.
- [x] Un job `interrupted` se puede reintentar.
- [x] Al arrancar se limpian las carpetas de staging sin job activo.
- [x] Tests con `FakeEngine` que simula cuelgue y fallo.

## Comments

**2026-11-15 — Implementación.**

- **Cancelar** (`JobQueue.cancel`, `POST /api/jobs/{id}/cancel`): un job `queued` pasa a `canceled` bajo el lock de la cola (nunca se reclama). Uno activo marca el job como "cancelando", llama a `terminate()` al árbol de procesos y espera a que termine; pasados 5 s sin salir llama a `kill()` (2 s más de margen). El runner ve la marca, deja el job en `canceled` (sin `error`), borra el staging, y `_work` libera el slot (arranca el siguiente) y dispara `on_drained` si hay una actualización del motor retenida. Una cancelación que llega antes de que exista el proceso se aplica en `_set_handle` o, si el worker aún no empezó, el runner sale sin lanzar yt-dlp. La petición bloquea hasta el estado final (hasta ~7 s en el peor caso) y devuelve el job.
- **Carrera cancelar/completar**: decide el proceso. Si salió con código 0 antes de que el TERM surtiera efecto, el archivo ya está en el Destination y el job queda `completed`; la petición recibe 409 `job_not_cancelable`. Cualquier otra salida con la cancelación pedida es `canceled` (también si el proceso salió con error). Así el estado final es único y coherente con lo que hay en disco. Si el árbol no muere ni con KILL, la petición da 409 y el job pasa a `canceled` cuando el proceso por fin acabe.
- **Reintentar** (`JobQueue.retry`, `POST /api/jobs/{id}/retry`): `attempt + 1`, progreso, error, salida y marcas de tiempo a cero, y vuelve a `queued` al final de la cola. Desviación menor respecto de la spec: migración 3 añade `jobs.queued_at` (rellenada con `created_at`); la FIFO ordena por `COALESCE(queued_at, created_at), rowid` y `created_at` no se toca (el historial lo usa). El sello de un reintento es siempre posterior al mayor `queued_at` existente (un reloj grueso o congelado no deja adelantar a nadie). Staging limpio: `prepare_staging` ya vacía la carpeta al empezar cada Attempt; el job conserva batch, índice y opciones. Un reintento espera brevemente a que el slot del Attempt anterior se libere (el runner publica el estado final justo antes) para no pisar `_active`.
- **UI**: "Cancelar" en tarjetas `queued` (inmediato) y `downloading`/`processing` (confirmación en línea "¿Cancelar esta descarga?"), "Reintentar" en `failed`/`canceled`/`interrupted`, "Intento N" desde el segundo, estado "Cancelada". Un error de la acción muestra un aviso y vuelve a pedir la lista (p. ej. el job ya había terminado). Los comandos reutilizan `EnqueueError` para el código de la API.
- **Tests**: `test_cancel_retry.py` (cola vs activo, TERM vs KILL, proceso sordo, cancelar antes del proceso, slot liberado, actualización del motor pendiente, carrera, cada estado reintentable, 409/404, reintento al final de la cola, árbol de procesos real con padre e hijo —incluido uno que ignora TERM— sin huérfanos). Se corrigieron dos aserciones intermitentes de `test_queue.py` (orden de arranque de jobs paralelos) y se actualizaron los tests de migración (versión 3).
- **Verificación**: pytest ×8 seguidos (638), ruff check y format, Vitest (186) y build en verde. Real con `docker compose up --build` y `HOST_DOWNLOAD_DIR=.dev-data/downloads`: `aqz-KE-bpKQ` a 1080p cancelado a mitad de descarga por curl → `canceled`, `/data/staging` vacío, sin procesos `yt-dlp`/`ffmpeg`/`deno` (el contenedor no trae `ps`; se recorrió `/proc`), segundo cancel y retry de un job activo → 409; reintentado (attempt 2) y cancelado de nuevo, y un tercer intento completó con un solo archivo. Medios de prueba borrados. La UI solo se probó con tests de componente. Windows (taskkill /T) no se probó.

**2026-11-15 — Revisión del orquestador.** Checks repetidos (638 backend ×3, 186 frontend, ruff, build). Probado en el navegador integrado con Big Buck Bunny a 1080p: progreso en vivo (4 %, 9,8 de 275 MB, velocidad y tiempo restante), "Cancelar" pide confirmación y deja "Cancelada" sin procesos de `yt-dlp`/`ffmpeg`/Deno ni staging; "Reintentar" arranca "Intento 2", que se volvió a cancelar. Spec actualizada con `queued_at`, los `409` y la regla de la carrera cancelar/completar. Windows `taskkill /T` sigue sin probarse en real.
