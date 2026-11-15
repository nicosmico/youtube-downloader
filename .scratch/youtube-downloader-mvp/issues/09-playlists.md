# 09: Playlists

**What to build:** Una URL de playlist o de canal muestra hasta 500 `Entry` en el preview, con aviso si hay más. Las disponibles vienen seleccionadas por defecto y se pueden deseleccionar; las privadas o eliminadas aparecen deshabilitadas con su motivo. Al encolar se crea un `Batch` con un `DownloadJob` por `Entry` elegida. Los archivos se guardan en una subcarpeta con el título saneado de la playlist, numerados según su posición en ella; si la carpeta ya existe se reutiliza. La cola respeta la concurrencia máxima.

**Blocked by:** 07 (Opciones nivel 1).

**Status:** ready-for-agent

- [ ] El preview de playlist y de canal lista las `Entry` sin descargar, con `truncated` si superan 500.
- [ ] Las `Entry` disponibles vienen seleccionadas y se pueden deseleccionar; las no disponibles se muestran deshabilitadas con motivo.
- [ ] Encolar crea un `Batch` y un job por `Entry` seleccionada; el servidor rechaza URLs que no sean de YouTube.
- [ ] Los archivos se guardan en `DOWNLOAD_DIR/<folder_name>/<NN> - <título>.<ext>` (por defecto `~/Downloads`), con `NN` según la posición en la playlist.
- [ ] `folder_name` es válido en macOS y Windows; descargar la misma playlist dos veces reutiliza la carpeta y resuelve colisiones por archivo.
- [ ] Los jobs de un batch son independientes entre sí.
- [ ] Tests unitarios de saneado y numeración, y tests de integración con `FakeEngine` para preview y descarga de playlists.
