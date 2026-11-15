# Spec: youtube-downloader MVP

**Status:** ready-for-agent

## Problem Statement

Descargar videos o audio de YouTube con `yt-dlp` exige usar una terminal, conocer flags y mantener actualizados `yt-dlp`, `ffmpeg` y, desde 2025, un runtime JavaScript. El usuario quiere una aplicación visual, multiplataforma (macOS y Windows), que no le pida instalar Python, Node, Deno ni `ffmpeg`, y que le permita descargar contenido público con una cola persistente y progreso visible.

## Solution

Un ejecutable que levanta un servidor local, abre el navegador por defecto en una SPA y descarga mediante un `Engine` externo que la propia app instala y actualiza. Solo acepta URLs de YouTube. La UI, en español, expone solo las opciones de nivel 1: URL, `DownloadMode`, `Quality` o `AudioFormat`, y `Preset`. Todo se guarda en `~/Downloads`.

## User Stories

1. Como usuario, quiero pegar una URL de YouTube y ver la información del medio automáticamente, para confirmar qué voy a descargar antes de encolar.
2. Como usuario, quiero ver título, miniatura, duración y autor en el `MediaPreview`, para reconocer el contenido de un vistazo.
3. Como usuario, quiero ver las calidades realmente disponibles de un video, para elegir una que exista y no una etiqueta genérica.
4. Como usuario, quiero que una URL de playlist o de canal me muestre sus `Entry` (hasta 500), para saber cuántos videos se van a descargar.
5. Como usuario, quiero que todas las `Entry` disponibles vengan seleccionadas por defecto, para encolar todo con un clic.
6. Como usuario, quiero poder deseleccionar `Entry`, para bajar solo una parte.
7. Como usuario, quiero un mensaje claro cuando el contenido es privado, requiere login, no está disponible, es un directo o estreno, es un mix automático o no es de YouTube, para entender qué acepta la app.
8. Como usuario, quiero que el preview no descargue nada, para inspeccionar sin gastar datos ni disco.
9. Como usuario, quiero elegir modo video con calidad `best`, `2160p`, `1080p`, `720p` o `480p`, para controlar el tamaño y la resolución.
10. Como usuario, quiero elegir modo audio en `mp3`, `m4a` u `opus`, para obtener solo la pista de sonido.
11. Como usuario, quiero guardar la combinación actual de modo y calidad como `Preset`, para reutilizarla después.
12. Como usuario, quiero aplicar un `Preset` con un clic, para no repetir la configuración en cada descarga.
13. Como usuario, quiero renombrar y eliminar `Preset`, para mantener mi lista ordenada.
14. Como usuario, quiero que la app impida combinaciones inválidas, para no encolar un job que va a fallar.
15. Como usuario, quiero que un video suelto genere un solo `DownloadJob`, para verlo y controlarlo individualmente.
16. Como usuario, quiero que una playlist genere un `Batch` con un `DownloadJob` por `Entry`, para cancelar o reintentar uno sin afectar al resto.
17. Como usuario, quiero ver el progreso de cada job en porcentaje, bytes, velocidad y ETA, para saber cuánto falta.
18. Como usuario, quiero que se ejecuten como máximo dos descargas a la vez, para no saturar la red ni el equipo.
19. Como usuario, quiero cancelar un job en cola o en curso, para arrepentirme sin cerrar la app.
20. Como usuario, quiero reintentar un job fallido, cancelado o interrumpido, para recuperarlo sin volver a pegar la URL.
21. Como usuario, quiero ver un `History` con el estado final de cada job, para saber qué se descargó y qué falló.
22. Como usuario, quiero quitar una entrada del `History` sin borrar el archivo descargado, para limpiar la vista sin perder contenido.
23. Como usuario, quiero que la `Queue` y el `History` sobrevivan al cierre de la app, para no perder trabajo.
24. Como usuario, quiero que los jobs interrumpidos queden marcados y sean reintentables al reabrir, para retomar lo que quedó a medias.
25. Como usuario, quiero un botón para abrir la carpeta de descargas, para encontrar los archivos.
26. Como usuario, quiero que los videos sueltos se guarden en `~/Downloads` y las playlists en su propia subcarpeta, para mantener el destino ordenado.
27. Como usuario, quiero que dos videos con el mismo título generen archivos distintos y nunca se sobrescriban, para no perder descargas.
28. Como usuario, quiero ver el estado del `Engine` y saber si está listo, instalándose o con error, para entender por qué no puedo descargar todavía.
29. Como usuario, quiero que la app descargue el `Engine` en el primer arranque, para no instalar nada a mano.
30. Como usuario, quiero actualizar `yt-dlp` desde la UI o de forma automática, para seguir descargando cuando YouTube cambie.
31. Como usuario, quiero que la app abra el navegador sola al ejecutarla, para no escribir ninguna URL.
32. Como usuario, quiero que una segunda ejecución reutilice la instancia abierta, para no tener dos servidores ni dos colas.
33. Como usuario, quiero cerrar la aplicación desde la UI de forma ordenada, para no dejar procesos huérfanos.
34. Como usuario, quiero que varias pestañas muestren el mismo estado en vivo, para seguir la cola desde donde esté.
35. Como usuario, quiero que al volver a una pestaña suspendida el estado se recupere, para no quedarme con datos viejos.
36. Como usuario, quiero mensajes de error accionables cuando falla una descarga, para saber si reintentar o cambiar algo.
37. Como usuario, quiero que la app solo escuche en mi equipo, para no exponer descargas a la red local ni a internet.
38. Como usuario, quiero que el ejecutable funcione en macOS y Windows sin Python ni Node instalados, para compartirlo con otras personas.
39. Como usuario, quiero que la app se cierre sola si cierro todas las pestañas y no queda nada en cola, para no dejar un proceso invisible corriendo.
40. Como usuario, quiero que los archivos de una playlist lleven su número de orden, para conservar la secuencia original.
41. Como usuario, quiero ver las `Entry` privadas o eliminadas de una playlist deshabilitadas y con su motivo, para saber por qué no se descargarán.
42. Como usuario, quiero mostrar en Finder o Explorer el archivo de un job completado, para encontrarlo sin buscar.
43. Como usuario, quiero que los videos se reproduzcan con el reproductor de mi sistema siempre que la calidad elegida lo permita, para no instalar nada más.
44. Como usuario, quiero descargar el ejecutable desde una página de releases, para compartirlo con un enlace estable.

## Implementation Decisions

### Forma de la aplicación

- Un único proceso empaquetado con PyInstaller en modo `onedir`.
- El `Launcher` elige un puerto libre con bind a `127.0.0.1:0`, escribe `runtime.json` con `{pid, port, startedAt}` y abre el navegador por defecto. `--no-browser` o `OPEN_BROWSER=0` desactiva la apertura (usado en Docker).
- `DATA_DIR` y `DOWNLOAD_DIR` se pueden sobrescribir por variable de entorno; sus defaults son `~/.youtube-downloader` y `~/Downloads`. La UI no expone un selector de carpeta.
- Solo en desarrollo, `BIND_HOST` y `PORT` fijan la interfaz y el puerto para que Docker pueda publicarlo (ver ADR-0008).
- `Single Instance`: un lock de archivo en `$DATA_DIR` evita dos arranques simultáneos. Si `runtime.json` existe y `GET /api/health` responde con el identificador de la app, se abre esa instancia y el segundo proceso termina.
- El apagado se dispara desde la UI (`POST /api/system/shutdown`), por señal o por `Idle Shutdown`, cancelando jobs activos y marcándolos `interrupted`.
- `Idle Shutdown`: si pasan 10 minutos sin clientes SSE conectados, sin jobs `queued`, `downloading` o `processing` y sin instalación del `Engine` en curso, la app se apaga ordenadamente. El temporizador se reinicia con cualquier conexión.

### Frontend

- SPA en Angular (versión estable vigente, componentes standalone y signals) compilada a estáticos y servida por FastAPI en `/`.
- UI en español; los textos viven centralizados para poder traducirlos después.
- Sin CORS: un solo origen.
- Angular consume REST para comandos y SSE para eventos.
- Al reconectar SSE, el cliente rehidrata con `GET /api/jobs`; no depende de eventos perdidos.
- La `Queue` muestra los jobs `queued`, `downloading` y `processing`. El `History` muestra los terminales; los que no están `completed` ofrecen "Reintentar" y los `completed` ofrecen "Mostrar en Finder/Explorer".
- Para un video suelto, `best` siempre está disponible, más cada tope (`2160p`, `1080p`, `720p`, `480p`) menor o igual al lado menor máximo del video; por debajo de 480 solo queda `best`. La UI deshabilita el resto. Para playlists muestra todas, porque `--flat-playlist` no trae formatos.
- Junto a `2160p` la UI indica que el archivo puede requerir un reproductor como VLC (ADR-0009).

### URLs aceptadas

- Solo `youtube.com`, `www.youtube.com`, `m.youtube.com`, `music.youtube.com` y `youtu.be` (ADR-0006). Cualquier otro dominio se rechaza con `unsupported_site` sin invocar `yt-dlp`.
- Una URL con `v=` (o `youtu.be/<id>`, `/shorts/<id>`) es un video, aunque lleve `list=`. En ese caso la respuesta incluye `playlistUrl` y la UI ofrece "ver playlist completa".
- Una URL de lista (`/playlist?list=`) o de canal (`/@handle`, `/channel/…`, `/c/…`, `/user/…` y sus pestañas) es una `Playlist`.
- Los mixes automáticos (`list=RD…`) se rechazan con `mix_playlist`.
- Los directos y estrenos pendientes se rechazan con `live_content`: se aceptan `live_status` `not_live`, `was_live` o ausente; cualquier otro valor (`is_live`, `is_upcoming`, `post_live`, desconocido) se rechaza. Un estreno pendiente o un directo terminado sin grabación hacen fallar `yt-dlp -J` ("This live event will begin…"), y ese error de stderr también se traduce a `live_content`.
- El preview de una `Playlist` lista como máximo 500 `Entry` (`--playlist-end 500`) y marca `truncated: true` si hay más.

### Engine

- Binarios externos en `$DATA_DIR/bin`: `yt-dlp`, `ffmpeg`, `ffprobe` y `deno`. `ENGINE_BIN_DIR` permite sobrescribir esa ruta en desarrollo y CI.
- Plataformas de producción: macOS arm64 y Windows x64. Los binarios Linux solo se usan en desarrollo (arm64, Docker en Apple Silicon) y CI (x64).
- Fuentes, validadas en el spike (versiones de referencia: `yt-dlp` 2026.10.26, Deno 2.9.8, FFmpeg 9.0.2):

| Binario | macOS arm64 | Windows x64 | Linux arm64 / x64 | Hash |
| :--- | :--- | :--- | :--- | :--- |
| `yt-dlp` | `yt-dlp_macos` | `yt-dlp.exe` | `yt-dlp_linux_aarch64` / `yt-dlp_linux` | `SHA2-256SUMS` del release (dinámico) |
| Deno | `deno-aarch64-apple-darwin.zip` | `deno-x86_64-pc-windows-msvc.zip` | `deno-aarch64-unknown-linux-gnu.zip` / `deno-x86_64-unknown-linux-gnu.zip` | Fijado en el código |
| `ffmpeg`, `ffprobe` | martin-riedl, un zip por binario | Gyan essentials (`GyanD/codexffmpeg`), un zip con ambos en `bin/` | martin-riedl, un zip por binario | Fijado en el código |

- La última versión de `yt-dlp` se obtiene de la redirección pública `https://github.com/yt-dlp/yt-dlp/releases/latest` (cabecera `Location` → `…/releases/tag/<tag>`), no de `api.github.com`: no tiene el límite de 60 consultas por hora por IP ni necesita token. La app nunca lee tokens del entorno.
- Todas las conexiones HTTPS de la app usan un contexto SSL explícito con los certificados del sistema (`truststore`: Llavero en macOS, almacén de Windows), con `certifi` como respaldo. El OpenSSL del Python empaquetado no trae certificados en un equipo de usuario.
- El `yt-dlp` oficial ya incluye `yt-dlp-ejs`. BtbN se descarta para Windows porque borra sus releases antiguos y el hash fijado dejaría de ser descargable.
- Cada binario se descarga a un archivo temporal, se verifica por SHA-256, recibe permiso de ejecución en macOS y se activa con `rename` atómico. Al arrancar se borran restos `.old` y `.new`.
- Verificación con `yt-dlp --version`, `ffmpeg -version`, `ffprobe -version` y `deno --version`. Si cualquiera falla, incluido Deno, el Engine queda en `error`: no se descarga en modo degradado.
- Estados: `missing → installing → ready | error`.
- Actualización de `yt-dlp` al arrancar si `engine.json` tiene más de 24 h, cada 24 h mientras la app está abierta, o manualmente desde la UI. No se usa `-U`: la app consulta el último release, descarga el binario nuevo a un temporal, lo verifica contra `SHA2-256SUMS` y lo intercambia con el actual (el viejo pasa a `.old` y se borra).
- Durante la actualización la `Queue` deja de despachar jobs nuevos, espera a que terminen los activos, intercambia el binario y reanuda. Así ningún proceso retiene el binario viejo, que en Windows impediría borrarlo. Vale tanto para la actualización automática como para la manual.
- La instalación es incremental: un reintento no vuelve a descargar los binarios ya instalados. `engine.json` guarda también el hash del archivo descargado (`archiveSha256`) para detectar cuándo una nueva versión de la app fija otra versión de `ffmpeg`, `ffprobe` o Deno.
- `ffmpeg`, `ffprobe` y Deno solo cambian con una nueva versión de la app.
- `engine.json` en `$DATA_DIR` guarda versión y hash de cada binario y la fecha del último chequeo de `yt-dlp`; se reescribe tras cada actualización.
- Las descargas quedan bloqueadas hasta que el Engine esté `ready`.

### Dominio y persistencia

- Un `DownloadJob` por video. Una playlist se modela como `Batch` con N jobs; un video suelto no tiene `Batch` (`batch_id` nulo).
- Estados del job: `queued → downloading → processing → completed`, con salidas laterales a `failed`, `canceled` e `interrupted`.
- `completed` solo se marca cuando el archivo final está en la `Destination`.
- Los jobs en `downloading` o `processing` al arrancar pasan a `interrupted` ("La aplicación se cerró durante la descarga") y se borra su staging; no se reanudan solos. Los `queued` sí se reanudan, en orden.
- El apagado deja de despachar, termina los árboles de procesos activos (terminate, 3 s, kill, 2 s) y marca esos jobs `interrupted`.
- Concurrencia máxima: 2. Selección FIFO por `created_at`.
- Solo los jobs en estado terminal se pueden quitar del `History`; borrar uno activo o en cola responde `409`.
- Persistencia en SQLite con WAL en `$DATA_DIR/db.sqlite3` y migraciones numeradas:

```sql
CREATE TABLE batches (
  id TEXT PRIMARY KEY,
  source_url TEXT NOT NULL,
  title TEXT NOT NULL,
  folder_name TEXT NOT NULL,
  entry_count INTEGER NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE jobs (
  id TEXT PRIMARY KEY,
  batch_id TEXT REFERENCES batches(id),
  playlist_index INTEGER,
  url TEXT NOT NULL,
  title TEXT,
  mode TEXT NOT NULL CHECK (mode IN ('video','audio')),
  quality TEXT,
  audio_format TEXT,
  status TEXT NOT NULL,
  progress_percent REAL NOT NULL DEFAULT 0,
  downloaded_bytes INTEGER,
  total_bytes INTEGER,
  speed REAL,
  eta INTEGER,
  output_path TEXT,
  error TEXT,
  attempt INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  started_at TEXT,
  finished_at TEXT
);

CREATE TABLE presets (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  mode TEXT NOT NULL,
  quality TEXT,
  audio_format TEXT,
  created_at TEXT NOT NULL
);
```

- Se siembran los presets `Mejor video` y `MP3` si la tabla está vacía.

### API REST

| Método | Ruta | Contrato |
| :--- | :--- | :--- |
| `GET` | `/api/health` | Identificador y versión de la app, Engine (mismo objeto que `/api/system/engine`), puerto. |
| `POST` | `/api/preview` | `{url}` → `MediaPreview`. |
| `POST` | `/api/jobs` | `{url, mode, quality?, audioFormat?, title?, entries?}` → `{batchId \| null, jobs[]}`. `title` viene del `MediaPreview` del cliente. |
| `GET` | `/api/jobs` | `{jobs, nextBefore}`, del más reciente al más antiguo. Filtros: `status` (lista separada por comas), `limit`, `before` (id de job). |
| `GET` | `/api/jobs/{id}` | `DownloadJob`. |
| `POST` | `/api/jobs/{id}/cancel` | Cancela job en cola o activo. |
| `POST` | `/api/jobs/{id}/retry` | Reencola job `failed`, `canceled` o `interrupted` como nuevo `Attempt`. |
| `POST` | `/api/jobs/{id}/reveal` | Muestra el archivo de un job `completed` en Finder/Explorer (acción del host). |
| `DELETE` | `/api/jobs/{id}` | Quita un job terminal del `History`; no toca el archivo. `409` si no es terminal. |
| `GET` | `/api/events` | Stream SSE. |
| `GET` | `/api/presets` | Lista de `Preset`. |
| `POST` | `/api/presets` | Crea `Preset`. |
| `PATCH` | `/api/presets/{id}` | Edita `Preset`. |
| `DELETE` | `/api/presets/{id}` | Elimina `Preset`. |
| `GET` | `/api/system/engine` | Estado, mensaje y versiones del Engine. |
| `POST` | `/api/system/engine/install` | Reintenta una instalación fallida; solo descarga los binarios que faltan. `202`, o `409` si ya hay una operación en curso. |
| `POST` | `/api/system/engine/update` | Fuerza actualización de `yt-dlp`. `202`, también con descargas activas: el Engine queda con `updatePending` y se aplica al terminar. `409` si ya hay una pendiente o en curso (`engine_busy`), si no está listo (`engine_not_ready`) o con `ENGINE_BIN_DIR` (`engine_external`). |
| `POST` | `/api/system/open-downloads` | Abre `DOWNLOAD_DIR` en Finder/Explorer. `200`, `501 open_unavailable` (sin abridor, p. ej. en Docker) o `500 open_failed`. |
| `POST` | `/api/system/shutdown` | Apagado ordenado. |

`MediaPreview` incluye `kind` (`video` o `playlist`), `id`, `url`, título, miniatura, duración, autor, `availableQualities`, `maxQuality`, `maxResolution` (lado menor máximo, en píxeles), `playlistUrl` si la URL de video venía de una lista, y para playlists `entries` y `truncated`. Cada `Entry` lleva `{id, url, index, title, duration, available, unavailableReason?}`.

Al encolar una playlist, `entries` lista las `Entry` elegidas con su `index` y título; el servidor valida que sus URLs sean de YouTube.

Los errores usan `{code, message, detail?}`. El `message` de los errores que ve el usuario (Engine, preview, jobs) va en español; los rechazos de seguridad, que no llegan a la UI, pueden ir en inglés. Las operaciones que necesitan el Engine responden `409` con `engine_not_ready` si no está `ready`. Códigos de preview: `invalid_url`, `unsupported_site`, `mix_playlist`, `live_content`, `not_public`, `unavailable` (`422`); `timeout` (`504`); `preview_failed` (`502`, cualquier otro fallo de `yt-dlp`, con mensaje saneado); `engine_not_ready` (`409`). El preview de video usa un tiempo límite de 30 s y, si se agota, mata el árbol de procesos.

### Eventos SSE

| Evento | Condición |
| :--- | :--- |
| `job.updated` | Alta, cambio de estado o progreso, con throttle de 1/s por job. |
| `job.removed` | Job quitado del `History`. |
| `engine.updated` | Cambio de estado o versión del Engine. |
| `queue.updated` | Cambio en cola o jobs activos, con `{active, queued}`. |
| `shutdown` | La app va a cerrarse, con el motivo (`user`, `signal`, `idle`). |

Al conectar, el stream envía primero el estado actual (`engine.updated` y `queue.updated`). Heartbeat cada 15 s como comentario SSE (`: heartbeat`), que `EventSource` ignora.

### Runner y `yt-dlp`

- Todas las invocaciones, incluido el preview, pasan `--ffmpeg-location <bin>` y `--js-runtimes deno:<ruta absoluta de deno>`. Sin `--ffmpeg-location` el formato por defecto degrada a uno combinado de baja calidad; sin `--js-runtimes`, `yt-dlp` solo busca Deno en el `PATH`.
- Preview de video: `yt-dlp -J --no-warnings --no-playlist <url>`.
- Preview de playlist: `yt-dlp -J --flat-playlist --playlist-end 500 --no-warnings <url>`.
- Descarga: `--no-playlist --newline --progress --no-overwrites --progress-template "download:PROGRESS%(progress)j" --progress-template "postprocess:POSTPROC%(progress)j" --print "before_dl:TOTAL%(filesize,filesize_approx)j" --print after_move:filepath -P <staging> -o "%(title)s.%(ext)s"`. `--print` implica `--quiet`, por eso se añade `--progress`; con `after_move` sí descarga.
- Video (ADR-0009), siempre con `--merge-output-format mp4` (mux con `-c copy`, sin recodificar):

| Quality | `-S` |
| :--- | :--- |
| `best` | `res,vcodec:h264,acodec:aac` |
| `2160p` | `res:2160,vcodec:h264,acodec:aac` |
| `1080p` | `res:1080,vcodec:h264,acodec:aac` |
| `720p` | `res:720,vcodec:h264,acodec:aac` |
| `480p` | `res:480,vcodec:h264,acodec:aac` |

  `res` mide el lado menor, así que un video vertical respeta la `Quality`. Si el video no llega al tope, se toma su máximo.
- Audio, siempre con `-x --audio-quality 0 --audio-format <fmt>`:

| AudioFormat | `-f` | Recodifica |
| :--- | :--- | :--- |
| `m4a` | `ba[acodec^=mp4a]/ba` | No, salvo que falte AAC |
| `opus` | `ba[acodec=opus]/ba` | No, salvo que falte Opus |
| `mp3` | `ba` | Siempre |

- Progreso: las líneas `PROGRESS` salen por stdout y las `POSTPROC` por stderr; el runner lee ambos streams. La última línea de stdout es la ruta de `after_move:filepath`.
- Con video y audio separados hay dos descargas seguidas, cada una con su `"status": "finished"`; ninguno marca el fin del job. La línea `TOTAL` (antes de descargar) da el tamaño esperado de todos los streams y es el denominador del porcentaje, que solo llega a 100 al terminar el último. Si falta, se suman los bytes de los streams terminados al del stream en curso (se distinguen por `filename`). `total_bytes` puede faltar y venir `total_bytes_estimate`. El porcentaje nunca retrocede.
- El job pasa a `processing` con el primer `POSTPROC` `started` cuyo `postprocessor` no sea `MoveFiles`. El `MoveFiles` de `yt-dlp` ocurre dentro del staging; `completed` solo llega tras el movimiento propio de la app (ADR-0010).
- Cancelación: `terminate()` al grupo de procesos y `kill()` tras 5 s. En Windows se termina el árbol completo (Job Object o equivalente) y los subprocesos se lanzan con `CREATE_NO_WINDOW`.
- Reintento: `attempt + 1` con carpeta de staging limpia.
- Los mensajes de error se sanean antes de exponerlos.

### Archivos

- Cada `Attempt` descarga en `$DATA_DIR/staging/<job_id>/` (ADR-0010). Al terminar, la app mueve el archivo a la `Destination` y marca `completed`. Cancelar o fallar borra el staging del job; al arrancar se limpian los staging sin job activo.
- Video suelto: `$DOWNLOAD_DIR/<nombre de yt-dlp>`.
- Playlist: `$DOWNLOAD_DIR/<Batch.folder_name>/<NN> - <nombre de yt-dlp>`. `NN` es el `index` de la `Entry` con ceros a la izquierda según `entry_count` (mínimo dos dígitos). `folder_name` es el título de la playlist saneado con reglas válidas en macOS y Windows; si la carpeta ya existe se reutiliza.
- Colisión: si el nombre final existe, se agrega ` (2)`, ` (3)`, etc. antes de la extensión. La elección del nombre y el movimiento ocurren bajo un lock para que dos jobs concurrentes no elijan el mismo.
- El movimiento tolera volúmenes distintos (copia y borrado) cuando `rename` no es posible.
- La ruta final se guarda en `outputPath`.

### Seguridad local

- Bind exclusivo a `127.0.0.1` en producción.
- Validación de `Host` contra `127.0.0.1:<puerto>` y `localhost:<puerto>`.
- Endpoints mutantes exigen `X-Requested-With: youtube-downloader` y validan `Origin` cuando está presente.
- Los binarios del `Engine` se verifican por SHA-256 antes de ejecutarse.
- Sin autenticación de usuario en el MVP.

### Entorno de desarrollo

- Backend y tests corren en Docker Compose sobre Linux, usando OrbStack en macOS. No se requiere Python en el host.
- Python 3.13 con `uv` dentro del contenedor; `uv.lock` versionado y la imagen construida con `uv sync --frozen`; `ruff` para lint y formato; `pytest` para tests.
- El build de Angular puede correr con Node local (ya instalado) o en un contenedor opcional.
- El contenedor escucha en `0.0.0.0:<PORT>`, Compose publica ese puerto en `127.0.0.1` del host, monta `~/Downloads` y `$DATA_DIR`, y arranca con `OPEN_BROWSER=0`. El host abre el navegador.
- Los tests de backend se ejecutan en el mismo contenedor que CI.
- "Abrir carpeta" y "Mostrar archivo" en desarrollo son acciones del host; el contenedor no puede abrir Finder ni Explorer.

### Empaquetado

- PyInstaller `onedir`, con los estáticos de Angular incluidos vía `--add-data` (separador `:` en macOS y `;` en Windows) y resueltos en ejecución con `sys._MEIPASS`.
- En Windows (`--noconsole`, sin stdout), uvicorn arranca con `log_config=None`; el logging de la app escribe a archivo en `$DATA_DIR`.
- macOS: `.app` arm64 con firma ad-hoc, distribuido en `.zip`. Mínimo macOS 13.
- Windows: carpeta con `.exe` x64 sin consola, distribuida en `.zip`. Windows 10/11.
- Los builds se ejecutan en GitHub Actions con matriz `macos-latest` y `windows-latest`; Docker no participa en el empaquetado nativo.
- Un tag `v*` publica un GitHub Release con ambos `.zip`. Los artefactos de Actions quedan para builds de prueba.
- Sin firma ni notarización en el MVP.

## Testing Decisions

Un buen test verifica **comportamiento externo**, no detalles de implementación: dada una entrada, qué observa el usuario (respuesta HTTP, estado del job, archivo en disco, evento SSE). Debe ser determinista, sin red y sin depender del reloj real.

Seams acordados:

1. **Backend — API HTTP.** FastAPI con `TestClient`, directorio de datos temporal, SQLite temporal y un `FakeEngine` que reemplaza a `yt-dlp` en el borde de subprocess. Cubre preview, alta de jobs, cola, concurrencia, persistencia, cancelación, reintento, reconciliación de interrumpidos, staging y movimiento final, SSE, `Idle Shutdown` y validaciones de seguridad.
2. **Frontend — servicios y componentes Angular.** HTTP y SSE mockeados. Cubre renderizado de preview, selección de playlist, opciones, progreso, presets, `History` y rehidratación al reconectar.

El `FakeEngine` debe poder: devolver JSON de preview de video, playlist, directo y entradas no disponibles; emitir líneas `PROGRESS` predecibles por stdout, incluidas dos descargas seguidas (video y audio); simular post-procesado con líneas `POSTPROC` por stderr; escribir el archivo final en staging e imprimir su ruta; fallar con un mensaje; y quedarse colgado para probar cancelación.

Decisiones de prueba:

- Tests unitarios del clasificador de URLs, parser de progreso, saneado de carpetas, numeración de playlist, colisiones, máquina de estados y validadores.
- Tests de contrato de los argumentos que se pasan a `yt-dlp` por modo y calidad.
- Tests de integración de la API con el `FakeEngine`, sin red.
- Tests del instalador del Engine con descargador simulado, incluida la verificación SHA-256.
- Los tests de backend corren en el contenedor Linux y en CI; no dependen de macOS.
- Descargas reales contra YouTube solo como E2E manual opt-in (`pytest -m network`).
- La UI se prueba con servicios mockeados; el E2E de navegador queda fuera del MVP.
- Los smoke tests de los ejecutables corren en los runners macOS y Windows de GitHub Actions.
- Criterio de no-regresión: la suite por defecto nunca depende de red.

No hay código previo; estos tests establecen la convención del repo.

## Out of Scope

- Ícono de bandeja del sistema.
- Selector de carpeta en la UI y destinos distintos de `~/Downloads` en producción. El override por entorno es solo para desarrollo.
- Cookies, cuentas, videos privados, con edad o con login.
- Sitios distintos de YouTube, directos, estrenos pendientes y mixes automáticos.
- Más de 500 `Entry` por playlist o canal.
- Subtítulos, incrustar miniatura/metadatos, recorte por tiempo y flags extra de `yt-dlp`.
- SponsorBlock y límites de velocidad o de red.
- Configuración de concurrencia desde la UI (fija en 2).
- Reanudación automática de jobs interrumpidos.
- Avisar al volver a descargar un medio ya descargado: el `History` no garantiza que el archivo siga en disco, y la colisión ` (2)` ya evita sobrescribir.
- Idiomas distintos del español en la UI.
- Firma, notarización e instaladores.
- Auto-actualización del ejecutable.
- Macs Intel y Windows ARM.
- Acceso remoto o desde otros dispositivos.
- Docker como runtime del producto.
- Soporte de Linux para usuarios finales.

## Further Notes

- Las validaciones técnicas del spike (ticket 01) están en `spike-01-findings.md`; sus conclusiones ya están incorporadas en esta spec.
- Cerrar la pestaña del navegador no detiene la app de inmediato; "Cerrar aplicación" la cierra en el acto y `Idle Shutdown` la cierra tras 10 minutos de inactividad.
- La actualización del Engine no interrumpe jobs activos: pausa el despacho, espera a que terminen y luego intercambia el binario.
- Docker se usa solo en desarrollo y CI. La decisión y sus consecuencias están en el ADR-0008.
- En desarrollo, las rutas de `DOWNLOAD_DIR` y `DATA_DIR` son las del contenedor; "abrir carpeta" queda como acción del host.
- La implementación se organiza en los tickets de `.scratch/youtube-downloader-mvp/issues/`.
