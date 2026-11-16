# youtube-downloader

Aplicación de escritorio que descarga contenido público de YouTube usando `yt-dlp`, con una interfaz web servida localmente.

## Contenido y previsualización

**MediaPreview**:
Metadatos de una URL obtenidos antes de descargar: título, miniatura, duración, calidades disponibles y, si aplica, las `Entry` de la playlist.
_Evitar_: metadata, info, resultado de inspección

**Contenido público**:
Medio de YouTube accesible sin autenticación, cookies ni cuenta, y ya publicado (no en directo ni como estreno pendiente).
_Evitar_: contenido libre, video normal

**Playlist**:
URL de YouTube que agrupa varios medios: una lista de reproducción o un canal. Una URL que apunta a un video dentro de una lista es un video, no una playlist.
_Evitar_: lista, álbum

**Entry**:
Cada medio que lista el `MediaPreview` de una `Playlist`, en su orden original; el usuario elige cuáles descargar.
_Evitar_: item, elemento, pista

## Descargas y cola

**DownloadJob**:
Descarga de un único medio; unidad de encolado, progreso, cancelación y reintento.
_Evitar_: tarea, descarga (como unidad), item

**Attempt**:
Cada ejecución de un `DownloadJob`. Reintentar crea un nuevo `Attempt` del mismo job, no un job nuevo.
_Evitar_: reintento (como sustantivo), ejecución

**Queue**:
`DownloadJob` en espera o en curso, atendidos por orden de llegada con un máximo de dos simultáneos.
_Evitar_: lista de espera, cola de tareas

**History**:
`DownloadJob` que alcanzaron un estado terminal: `completed`, `failed`, `canceled` o `interrupted`. Quitar un job del `History` no borra su archivo.
_Evitar_: registro, log, descargas anteriores

**Batch**:
Agrupación de los `DownloadJob` generados por una misma `Playlist`. Un video suelto no pertenece a ningún `Batch`.
_Evitar_: lote, grupo, playlist (para la agrupación)

**Job Status**:
Estado del ciclo de vida de un `DownloadJob`: `queued`, `downloading`, `processing`, `completed`, `failed`, `canceled`, `interrupted`.
_Evitar_: estado de la descarga, progreso

**Destination**:
Carpeta de descargas del usuario donde quedan los archivos terminados; cada `Batch` va en una subcarpeta con el título de su `Playlist`.
_Evitar_: ruta de salida, carpeta destino

## Opciones

**DownloadMode**:
Intención de un `DownloadJob`: `video` o `audio`.
_Evitar_: tipo, formato

**Quality**:
Tope de resolución de un `DownloadJob` en modo video, medido sobre el lado menor de la imagen: `best`, `2160p`, `1080p`, `720p`, `480p`.
_Evitar_: resolución, definición

**AudioFormat**:
Contenedor objetivo de un `DownloadJob` en modo audio: `mp3`, `m4a`, `opus`.
_Evitar_: códec, extensión

**Preset**:
Chip fijo del control de formato que rellena `DownloadMode` y `Quality` o `AudioFormat` de un clic. Hay solo dos, "Mejor video" (video, `best`) y "MP3" (audio, `mp3`); no los define ni los guarda el usuario.
_Evitar_: perfil, configuración guardada, preset personalizado

## Motor y aplicación

**Engine**:
Conjunto de programas externos (`yt-dlp`, `ffmpeg`, `ffprobe` y el runtime JavaScript Deno) que la app instala y actualiza por separado de su propio ejecutable.
_Evitar_: dependencias, herramientas, motor de descarga

**Launcher**:
Proceso que prepara el entorno, inicia el servidor local y abre el navegador.
_Evitar_: main, arranque

**Single Instance**:
Regla por la que solo puede existir un `Launcher` activo; un segundo intento reutiliza el servidor en curso.
_Evitar_: instancia única, bloqueo

**App Update Notice**:
Aviso, comprobado una sola vez al arrancar, de que existe un Release de la app más nuevo que el instalado; enlaza a su página y nunca actualiza por sí solo (ADR-0011).
_Evitar_: auto-update, actualización automática

**Idle Shutdown**:
Cierre automático de la app unos 15 s después de cerrarse la última pestaña, si la `Queue` está vacía y el `Engine` no está instalándose ni actualizándose; si aún no se ha conectado ninguna pestaña desde el arranque, espera 60 s. Una descarga en curso lo retrasa: los 15 s cuentan desde que la `Queue` se vacía. `IDLE_SHUTDOWN_SECONDS` lo ajusta (`0` lo desactiva).
_Evitar_: timeout, autocierre
