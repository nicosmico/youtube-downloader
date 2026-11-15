# 05: Descarga de un video end-to-end

**What to build:** Desde el preview, el usuario elige `best` y encola. El `DownloadJob` se persiste sin `Batch`, el runner ejecuta `yt-dlp` en la carpeta de staging del job, la UI muestra progreso, velocidad y ETA por SSE, y al terminar la app mueve el archivo a `DOWNLOAD_DIR` (en desarrollo, el volumen montado; en producción, `~/Downloads`) resolviendo colisiones bajo un lock (ADR-0010). La UI ofrece abrir la carpeta. Cubre los estados `downloading`, `processing`, `completed` y `failed`.

**Blocked by:** 04 (Preview de video).

**Status:** ready-for-agent

- [x] Un video público se descarga y el archivo aparece en `DOWNLOAD_DIR`; el staging del job queda vacío.
- [x] `POST /api/jobs` para un video suelto responde `batchId: null`.
- [x] La UI muestra progreso, velocidad y ETA en vivo.
- [x] `completed` solo se marca cuando el archivo final está en `DOWNLOAD_DIR`.
- [x] Dos descargas con el mismo título, incluso simultáneas, generan archivos distintos (` (2)`).
- [x] El movimiento final funciona entre volúmenes distintos (staging y descargas en montajes separados del contenedor).
- [x] El endpoint de abrir carpeta responde y la UI muestra el resultado; la apertura nativa en Finder se valida en el ticket 14.
- [x] Un fallo de `yt-dlp` deja el job `failed` con mensaje saneado y borra su staging.
- [x] Con el Engine sin `ready`, `POST /api/jobs` responde `engine_not_ready` y la UI no permite encolar.
- [x] Tests de integración con `FakeEngine` y tests de contrato de argumentos.

## Comments

**2026-11-15 — Implementación.** Backend: `app/db.py` (SQLite WAL, migraciones numeradas con `user_version`, `001` = `batches` + `jobs`), paquete `app/jobs/` (`models`, `repository`, `progress`, `arguments`, `files`, `failures`, `runner`, `queue`, `events`, `api`), `app/opener.py`, y `stream_process` + `ProcessHandle` en `engine/io.py`. Frontend: `EventStreamService` (una sola conexión SSE compartida por Engine y jobs), `JobsService`, componente `app-downloads`, botón "Descargar" en el preview.

Decisiones y desviaciones respecto a la spec (sin editarla):
- `POST /api/jobs` acepta `title` opcional (el cliente envía el del `MediaPreview`). Adición a la spec.
- `GET /api/jobs` responde `{jobs, nextBefore}`, de más nuevo a más viejo; `before` es el id del último job de la página anterior; `status` acepta uno o varios separados por coma.
- `POST /api/system/open-downloads` responde 200 `{status: "opened"}`; sin Finder/Explorer (Linux/Docker) responde 501 `open_unavailable` con mensaje en español; fallo del gestor de archivos, 500 `open_failed`.
- `mode: "audio"` responde 422 `audio_unsupported` (marcado `TICKET-07`); las playlists, 422 `playlist_unsupported` (`TICKET-09`). Cualquier `Quality` de video usa la tabla `-S`.
- El job pasa a `downloading` al reclamarlo el despachador (FIFO por `created_at`, límite 2); la UI lo ve como `queued` solo un instante.
- `processing` solo aparece si `yt-dlp` ejecuta un postprocesador distinto de `MoveFiles` (p. ej. `Merger`). Un video con un único stream combinado ("Me at the zoo") va de `downloading` a `completed` sin pasar por `processing`.
- Porcentaje del job: suma de bytes de todos los streams vistos, nunca retrocede. Mientras corre el stream de video el total aún no incluye al de audio, así que el porcentaje puede llegar a 100 y esperar hasta que el audio termina.
- El progreso se persiste y publica como máximo 1/s por job; el último valor viaja con el cambio de estado (`processing`/`completed`).
- `queue.updated` lleva `{active, queued}` (conteos).
- Al arrancar se borra todo el staging (nada corre aún) y los `queued` se reanudan. NO hay reconciliación de `downloading`/`processing` a `interrupted` (ticket 06): un job que quedó así tras cerrar la app sigue con ese estado. Tampoco se pausa el despacho durante la actualización de `yt-dlp` (ticket 06): `EngineManager.can_update` sigue sin conectar con la cola.
- `create_app` recibe `download_dir` (el launcher pasa `Settings.download_dir`); ahora crea `db.sqlite3` al construirse, así que el test "el preview no crea archivos" ya no exige que no exista.
- Los manejadores de proceso (`ProcessHandle`, con `terminate()`/`kill()`) quedan accesibles en `JobQueue.handle(job_id)` para el ticket 10.

Verificación: pytest 386 (+ `pytest -m network` real de "Me at the zoo": OK), ruff check/format, Vitest 119, build. Con `HOST_DOWNLOAD_DIR=$PWD/.dev-data/downloads docker compose up --build` y `curl`: dos descargas simultáneas del mismo video terminaron `completed` con `Me at the zoo.mp4` y `Me at the zoo (2).mp4` (una tercera, ` (3)`), el staging quedó vacío y el movimiento cruzó volúmenes reales (`/data` y `/downloads` son montajes distintos). Eventos SSE `job.updated` y `queue.updated` observados con `curl -N`. `open-downloads` respondió 501 en el contenedor. La UI solo se probó con tests de componente, no en un navegador real; la apertura nativa de Finder queda para el ticket 14.

**2026-11-15 — Revisión: total conocido y tests deterministas.** El runner pasa también `--print "before_dl:TOTAL%(filesize,filesize_approx)j"`; el parser usa ese valor como denominador (`max(total, bytes)`), de modo que el porcentaje no llega a 100 tras el primer stream, y cae a la agregación anterior si es `null` o basura. La última línea de stdout sigue siendo `after_move:filepath`. Verificado contra `2PuFyjAs7JA` a 720p (video+audio separados): `TOTAL845176` = 665442 + 179734, y en la app real el job anuncia `totalBytes 845176` desde el primer evento y solo llega a 100 al terminar. Los tests de API usan un reloj congelado y los del runner un reloj inyectado, sin esperas reales; pytest 399 pasó 5 veces seguidas.
