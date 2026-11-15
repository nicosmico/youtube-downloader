# Spec: youtube-downloader MVP

**Status:** ready-for-agent

## Problem Statement

Descargar videos o audio de YouTube con `yt-dlp` exige usar una terminal, conocer flags y mantener actualizados `yt-dlp` y `ffmpeg`. El usuario quiere una aplicación visual, multiplataforma (macOS y Windows), que no le pida instalar Python, Node ni `ffmpeg`, y que le permita descargar contenido público con una cola persistente y progreso visible.

## Solution

Un ejecutable que levanta un servidor local, abre el navegador por defecto en una SPA y descarga mediante un `Engine` externo que la propia app instala y actualiza. La UI expone solo las opciones de nivel 1: URL, `DownloadMode`, `Quality` o `AudioFormat`, y `Preset`. Todo se guarda en `~/Downloads`.

## User Stories

1. Como usuario, quiero pegar una URL de YouTube y ver la información del medio automáticamente, para confirmar qué voy a descargar antes de encolar.
2. Como usuario, quiero ver título, miniatura, duración y autor en el `MediaPreview`, para reconocer el contenido de un vistazo.
3. Como usuario, quiero ver las calidades realmente disponibles de un video, para elegir una que exista y no una etiqueta genérica.
4. Como usuario, quiero que una URL de playlist me muestre todas sus entradas, para saber cuántos videos se van a descargar.
5. Como usuario, quiero que todas las entradas de una playlist vengan seleccionadas por defecto, para encolar todo con un clic.
6. Como usuario, quiero poder deseleccionar entradas de una playlist, para bajar solo una parte.
7. Como usuario, quiero un mensaje claro cuando el contenido es privado, requiere login o no está disponible, para entender que la app solo trabaja con `Contenido público`.
8. Como usuario, quiero que el preview no descargue nada, para inspeccionar sin gastar datos ni disco.
9. Como usuario, quiero elegir modo video con calidad `best`, `2160p`, `1080p`, `720p` o `480p`, para controlar el tamaño y la resolución.
10. Como usuario, quiero elegir modo audio en `mp3`, `m4a` u `opus`, para obtener solo la pista de sonido.
11. Como usuario, quiero guardar la combinación actual de modo y calidad como `Preset`, para reutilizarla después.
12. Como usuario, quiero aplicar un `Preset` con un clic, para no repetir la configuración en cada descarga.
13. Como usuario, quiero renombrar y eliminar `Preset`, para mantener mi lista ordenada.
14. Como usuario, quiero que la app impida combinaciones inválidas, para no encolar un job que va a fallar.
15. Como usuario, quiero que un video suelto genere un solo `DownloadJob`, para verlo y controlarlo individualmente.
16. Como usuario, quiero que una playlist genere un `Batch` con un `DownloadJob` por video, para cancelar o reintentar uno sin afectar al resto.
17. Como usuario, quiero ver el progreso de cada job en porcentaje, bytes, velocidad y ETA, para saber cuánto falta.
18. Como usuario, quiero que se ejecuten como máximo dos descargas a la vez, para no saturar la red ni el equipo.
19. Como usuario, quiero cancelar un job en cola o en curso, para arrepentirme sin cerrar la app.
20. Como usuario, quiero reintentar un job fallido, cancelado o interrumpido, para recuperarlo sin volver a pegar la URL.
21. Como usuario, quiero ver un historial con el estado final de cada job, para saber qué se descargó y qué falló.
22. Como usuario, quiero borrar una entrada del historial sin borrar el archivo descargado, para limpiar la vista sin perder contenido.
23. Como usuario, quiero que la cola y el historial sobrevivan al cierre de la app, para no perder trabajo.
24. Como usuario, quiero que los jobs interrumpidos queden marcados y sean reintentables al reabrir, para retomar lo que quedó a medias.
25. Como usuario, quiero un botón para abrir la carpeta de descargas, para encontrar el archivo al terminar.
26. Como usuario, quiero que los videos sueltos se guarden en `~/Downloads` y las playlists en su propia subcarpeta, para mantener el destino ordenado.
27. Como usuario, quiero que dos videos con el mismo título generen archivos distintos y nunca se sobrescriban, para no perder descargas.
28. Como usuario, quiero ver el estado del `Engine` y saber si está listo, instalándose o con error, para entender por qué no puedo descargar todavía.
29. Como usuario, quiero que la app descargue `yt-dlp`, `ffmpeg` y `ffprobe` en el primer arranque, para no instalarlos a mano.
30. Como usuario, quiero actualizar `yt-dlp` desde la UI o de forma automática, para seguir descargando cuando YouTube cambie.
31. Como usuario, quiero que la app abra el navegador sola al ejecutarla, para no escribir ninguna URL.
32. Como usuario, quiero que una segunda ejecución reutilice la instancia abierta, para no tener dos servidores ni dos colas.
33. Como usuario, quiero cerrar la aplicación desde la UI de forma ordenada, para no dejar procesos huérfanos.
34. Como usuario, quiero que varias pestañas muestren el mismo estado en vivo, para seguir la cola desde donde esté.
35. Como usuario, quiero que al volver a una pestaña suspendida el estado se recupere, para no quedarme con datos viejos.
36. Como usuario, quiero mensajes de error accionables cuando falla una descarga, para saber si reintentar o cambiar algo.
37. Como usuario, quiero que la app solo escuche en mi equipo, para no exponer descargas a la red local ni a internet.
38. Como usuario, quiero que el ejecutable funcione en macOS y Windows sin Python ni Node instalados, para compartirlo con otras personas.

## Implementation Decisions

### Forma de la aplicación

- Un único proceso empaquetado con PyInstaller en modo `onedir`.
- El `Launcher` elige un puerto libre con bind a `127.0.0.1:0`, escribe `runtime.json` con `{pid, port, startedAt}` y abre el navegador por defecto. `--no-browser` o `OPEN_BROWSER=0` desactiva la apertura (usado en Docker).
- `DATA_DIR` y `DOWNLOAD_DIR` se pueden sobrescribir por variable de entorno; sus defaults son `~/.youtube-downloader` y `~/Downloads`. La UI no expone un selector de carpeta.
- `Single Instance`: si `runtime.json` existe y `GET /api/health` responde, se abre esa instancia y el segundo proceso termina.
- El apagado se dispara desde la UI (`POST /api/system/shutdown`) o por señal, cancelando jobs activos y marcándolos `interrupted`.

### Frontend

- SPA en Angular compilada a estáticos y servida por FastAPI en `/`.
- Sin CORS: un solo origen.
- Angular consume REST para comandos y SSE para eventos.
- Al reconectar SSE, el cliente rehidrata con `GET /api/jobs`; no depende de eventos perdidos.

### Engine

- Binarios externos en `$DATA_DIR/bin`: `yt-dlp`, `ffmpeg`, `ffprobe`. `ENGINE_BIN_DIR` permite sobrescribir esa ruta en desarrollo y CI.
- `yt-dlp` se obtiene del release oficial (`yt-dlp_macos`, `yt-dlp.exe` o `yt-dlp_linux` según la plataforma).
- `ffmpeg`/`ffprobe` se obtienen de un build estático validado por plataforma y arquitectura. Proveedor concreto a confirmar con un spike; candidatos: evermeet.cx o ffmpeg.martin-riedl.de para macOS, BtbN para Windows x64 y Linux.
- En desarrollo y CI sobre Linux se usan binarios Linux; Linux no es plataforma soportada para usuarios finales.
- Descarga a archivo temporal y `rename` atómico; permiso de ejecución en macOS.
- Verificación con `yt-dlp --version` y `ffmpeg -version`.
- Estados: `missing → installing → ready | error`.
- Actualización de `yt-dlp` con `-U` si `engine.json` tiene más de 24 h, o manual desde la UI. Si `-U` falla, se reinstala el release.
- Las descargas quedan bloqueadas hasta que el Engine esté `ready`.

### Dominio y persistencia

- Un `DownloadJob` por video; una playlist se modela como `Batch` con N jobs.
- Estados del job: `queued → downloading → processing → completed`, con salidas laterales a `failed`, `canceled` e `interrupted`.
- Los jobs en `downloading` o `processing` al arrancar pasan a `interrupted`; no se reanudan solos.
- Concurrencia máxima: 2. Selección FIFO por `created_at`.
- Persistencia en SQLite con WAL en `$DATA_DIR/db.sqlite3` y migraciones numeradas:

```sql
CREATE TABLE batches (
  id TEXT PRIMARY KEY,
  source_url TEXT NOT NULL,
  title TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE jobs (
  id TEXT PRIMARY KEY,
  batch_id TEXT REFERENCES batches(id),
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
| `GET` | `/api/health` | Versión de la app, estado del Engine, puerto. |
| `POST` | `/api/preview` | `{url}` → `MediaPreview`. |
| `POST` | `/api/jobs` | `{url, mode, quality?, audioFormat?, entries?}` → `{batchId, jobs[]}`. |
| `GET` | `/api/jobs` | Lista paginada con filtros `status`, `limit`, `before`. |
| `GET` | `/api/jobs/{id}` | `DownloadJob`. |
| `POST` | `/api/jobs/{id}/cancel` | Cancela job en cola o activo. |
| `POST` | `/api/jobs/{id}/retry` | Reencola job `failed`, `canceled` o `interrupted`. |
| `DELETE` | `/api/jobs/{id}` | Borra la entrada del historial; no toca el archivo. |
| `GET` | `/api/events` | Stream SSE. |
| `GET` | `/api/presets` | Lista de `Preset`. |
| `POST` | `/api/presets` | Crea `Preset`. |
| `PATCH` | `/api/presets/{id}` | Edita `Preset`. |
| `DELETE` | `/api/presets/{id}` | Elimina `Preset`. |
| `GET` | `/api/system/engine` | Estado y versiones del Engine. |
| `POST` | `/api/system/engine/update` | Fuerza actualización de `yt-dlp`. |
| `POST` | `/api/system/open-downloads` | Abre `DOWNLOAD_DIR` en Finder/Explorer (acción del host). |
| `POST` | `/api/system/shutdown` | Apagado ordenado. |

`MediaPreview` incluye `kind` (`video` o `playlist`), título, miniatura, duración, autor, calidades disponibles y `entries` para playlists. Los errores usan `{code, message, detail?}`.

### Eventos SSE

| Evento | Condición |
| :--- | :--- |
| `job.updated` | Alta, cambio de estado o progreso, con throttle de 1/s por job. |
| `job.removed` | Entrada de historial eliminada. |
| `engine.updated` | Cambio de estado o versión del Engine. |
| `queue.updated` | Cambio en cola o jobs activos. |
| `shutdown` | La app va a cerrarse. |

Heartbeat cada 15 s.

### Runner y `yt-dlp`

- Preview de video: `yt-dlp -J --no-warnings --no-playlist <url>`.
- Preview de playlist: `yt-dlp -J --flat-playlist --no-warnings <url>`.
- Descarga: `--newline`, `--no-overwrites`, `--progress-template "download:PROGRESS%(progress)j"`, `--print after_move:filepath`.
- Video: `-f "bv*[height<=H]+ba/b[height<=H]"`; `best` omite el tope; `--merge-output-format mp4` a validar para evitar recodificaciones.
- Audio: `-x --audio-quality 0 --audio-format <mp3|m4a|opus>`.
- Progreso: se parsean las líneas que empiezan con `PROGRESS` y contienen el JSON de `%(progress)j`.
- La fase de post-procesado se reporta como `processing`.
- Cancelación: `terminate()` al grupo de procesos y `kill()` tras 5 s.
- Reintento: `attempt + 1`, sin duplicar archivos.
- Los mensajes de error se sanean antes de exponerlos.

### Archivos

- Video suelto: `$DOWNLOAD_DIR/%(title)s.%(ext)s`.
- Playlist: `$DOWNLOAD_DIR/%(playlist_title)s/%(title)s.%(ext)s`.
- `DOWNLOAD_DIR` es `~/Downloads` en producción y se sobrescribe en desarrollo para apuntar al volumen montado.
- Colisión: si existe un archivo con el mismo stem al despachar, se agrega ` (2)`, ` (3)`, etc.
- La ruta final se toma de `--print after_move:filepath` y se guarda en `outputPath`.

### Seguridad local

- Bind exclusivo a `127.0.0.1`.
- Validación de `Host` contra `127.0.0.1:<puerto>` y `localhost:<puerto>`.
- Endpoints mutantes exigen `X-Requested-With: youtube-downloader` y validan `Origin` cuando está presente.
- Sin autenticación de usuario en el MVP.

### Entorno de desarrollo

- Backend y tests corren en Docker Compose sobre Linux, usando OrbStack en macOS. No se requiere Python en el host.
- El build de Angular puede correr con Node local (ya instalado) o en un contenedor opcional.
- El contenedor publica el puerto en `127.0.0.1`, monta `~/Downloads` y `$DATA_DIR`, y arranca con `OPEN_BROWSER=0`. El host abre el navegador.
- Los tests de backend se ejecutan en el mismo contenedor que CI.
- "Abrir carpeta" en desarrollo es una acción del host; el contenedor no puede abrir Finder ni Explorer.

### Empaquetado

- PyInstaller `onedir`, con los estáticos de Angular incluidos.
- macOS: `.app` con firma ad-hoc, distribuido en `.zip`.
- Windows: carpeta con `.exe`, distribuida en `.zip`.
- Los builds se ejecutan en GitHub Actions con matriz `macos-latest` y `windows-latest`; Docker no participa en el empaquetado nativo.
- Cada runner publica el artefacto correspondiente. Sin firma ni notarización en el MVP.

## Testing Decisions

Un buen test verifica **comportamiento externo**, no detalles de implementación: dada una entrada, qué observa el usuario (respuesta HTTP, estado del job, archivo en disco, evento SSE). Debe ser determinista, sin red y sin depender del reloj real.

Seams acordados:

1. **Backend — API HTTP.** FastAPI con `TestClient`, directorio de datos temporal, SQLite temporal y un `FakeEngine` que reemplaza a `yt-dlp` en el borde de subprocess. Cubre preview, alta de jobs, cola, concurrencia, persistencia, cancelación, reintento, reconciliación de interrumpidos, SSE y validaciones de seguridad.
2. **Frontend — servicios y componentes Angular.** HTTP y SSE mockeados. Cubre renderizado de preview, selección de playlist, opciones, progreso, presets, historial y rehidratación al reconectar.

El `FakeEngine` debe poder: devolver JSON de preview de video y playlist, emitir líneas `PROGRESS` predecibles, simular post-procesado, fallar con un mensaje, y quedarse colgado para probar cancelación.

Decisiones de prueba:

- Tests unitarios del parser de progreso, plantillas de salida, colisiones, máquina de estados y validadores.
- Tests de contrato de los argumentos que se pasan a `yt-dlp` por modo y calidad.
- Tests de integración de la API con el `FakeEngine`, sin red.
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
- Subtítulos, incrustar miniatura/metadatos, recorte por tiempo y flags extra de `yt-dlp`.
- SponsorBlock y límites de velocidad o de red.
- Configuración de concurrencia desde la UI (fija en 2).
- Reanudación automática de jobs interrumpidos.
- Firma, notarización e instaladores.
- Auto-actualización del ejecutable.
- Acceso remoto o desde otros dispositivos.
- Docker como runtime del producto.
- Soporte de Linux para usuarios finales.

## Further Notes

- Validaciones técnicas abiertas que deben resolverse con spikes antes de comprometer la implementación: proveedor de `ffmpeg` por arquitectura, viabilidad de `--merge-output-format mp4` sin recodificar, y build nativo en GitHub Actions.
- Cerrar la pestaña del navegador no detiene la app; el botón "Cerrar aplicación" es el mecanismo previsto en el MVP.
- La actualización del Engine no interrumpe jobs activos: se aplica al siguiente proceso.
- Docker se usa solo en desarrollo y CI. La decisión y sus consecuencias están en el ADR-0008.
- En desarrollo, las rutas de `DOWNLOAD_DIR` y `DATA_DIR` son las del contenedor; "abrir carpeta" queda como acción del host.
- La implementación se organiza en los tickets de `.scratch/youtube-downloader-mvp/issues/`.
