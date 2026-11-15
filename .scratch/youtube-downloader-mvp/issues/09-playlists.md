# 09: Playlists

**What to build:** Una URL de playlist muestra sus entradas en el preview, todas seleccionadas por defecto, y permite deseleccionar algunas. Al encolar se crea un `Batch` con un `DownloadJob` por entrada y los archivos se guardan en una subcarpeta con el título de la playlist. La cola respeta la concurrencia máxima.

**Blocked by:** 07 (Opciones nivel 1).

**Status:** ready-for-agent

- [ ] El preview de playlist lista las entradas sin descargar.
- [ ] Todas las entradas vienen seleccionadas por defecto y se pueden deseleccionar.
- [ ] Encolar crea un `Batch` y un job por entrada seleccionada.
- [ ] Los archivos se guardan en `DOWNLOAD_DIR/<playlist_title>/` (por defecto `~/Downloads`).
- [ ] Los jobs de un batch son independientes entre sí.
- [ ] Tests de integración con `FakeEngine` para preview y descarga de playlists.
