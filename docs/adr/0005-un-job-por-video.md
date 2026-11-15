---
status: accepted
---

# Una playlist es un `Batch` de jobs individuales

Descargar una playlist como un solo proceso impedía cancelar, reintentar o ver el progreso de un video sin afectar al resto. Decidimos expandir la playlist en N `DownloadJob`, uno por video, agrupados visualmente por `Batch`, con un máximo de dos descargas concurrentes.

## Consequences

- El progreso, la cancelación y el reintento son por video.
- La inspección de playlists usa `--flat-playlist`, que no trae formatos por entrada; la `Quality` se resuelve al descargar cada video como un tope de resolución.
- Las playlists grandes multiplican las peticiones a YouTube; la concurrencia baja (2) actúa como mitigación.
