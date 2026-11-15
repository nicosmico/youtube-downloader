# youtube-downloader

Aplicación de escritorio que descarga contenido público de YouTube usando `yt-dlp`, con una interfaz web servida localmente.

## Contenido y previsualización

**MediaPreview**:
Metadatos de una URL obtenidos antes de descargar: título, miniatura, duración, calidades disponibles y, si aplica, las entradas de la playlist.
_Evitar_: metadata, info, resultado de inspección

**Contenido público**:
Medio accesible sin autenticación, cookies ni cuenta.
_Evitar_: contenido libre, video normal

**Playlist**:
URL que agrupa varios medios. En la app siempre se expande en varios `DownloadJob`.
_Evitar_: lista, álbum

## Descargas y cola

**DownloadJob**:
Intento de descarga de un único medio; unidad de encolado, progreso, cancelación y reintento.
_Evitar_: tarea, descarga (como unidad), item

**Queue**:
Conjunto ordenado de `DownloadJob` pendientes de ejecución, con un máximo de dos ejecuciones simultáneas.
_Evitar_: lista de espera, cola de tareas

**Batch**:
Agrupación visual de los `DownloadJob` generados por una misma URL de playlist.
_Evitar_: lote, grupo, playlist (para la agrupación)

**Job Status**:
Estado del ciclo de vida de un `DownloadJob`: `queued`, `downloading`, `processing`, `completed`, `failed`, `canceled`, `interrupted`.
_Evitar_: estado de la descarga, progreso

**Destination**:
Carpeta fija donde el servidor escribe los archivos: `~/Downloads`, con una subcarpeta por playlist.
_Evitar_: ruta de salida, carpeta destino

## Opciones

**DownloadMode**:
Intención de un `DownloadJob`: `video` o `audio`.
_Evitar_: tipo, formato

**Quality**:
Resolución objetivo de un `DownloadJob` en modo video: `best`, `2160p`, `1080p`, `720p`, `480p`.
_Evitar_: resolución, definición

**AudioFormat**:
Contenedor objetivo de un `DownloadJob` en modo audio: `mp3`, `m4a`, `opus`.
_Evitar_: códec, extensión

**Preset**:
Combinación nombrada y reutilizable de `DownloadMode` y `Quality` o `AudioFormat`.
_Evitar_: perfil, configuración guardada

## Motor y aplicación

**Engine**:
Par de binarios externos `yt-dlp` y `ffmpeg` que la app descarga y actualiza por separado de su propio ejecutable.
_Evitar_: dependencias, herramientas, motor de descarga

**Launcher**:
Proceso que prepara el entorno, inicia el servidor local, elige un puerto libre y abre el navegador.
_Evitar_: main, arranque

**Single Instance**:
Regla por la que solo puede existir un `Launcher` activo; un segundo intento reutiliza el servidor en curso.
_Evitar_: instancia única, bloqueo
