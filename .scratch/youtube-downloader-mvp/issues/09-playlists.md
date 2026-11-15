# 09: Playlists

**What to build:** Una URL de playlist o de canal muestra hasta 500 `Entry` en el preview, con aviso si hay más. Las disponibles vienen seleccionadas por defecto y se pueden deseleccionar; las privadas o eliminadas aparecen deshabilitadas con su motivo. Al encolar se crea un `Batch` con un `DownloadJob` por `Entry` elegida. Los archivos se guardan en una subcarpeta con el título saneado de la playlist, numerados según su posición en ella; si la carpeta ya existe se reutiliza. La cola respeta la concurrencia máxima.

**Blocked by:** 07 (Opciones nivel 1).

**Status:** ready-for-agent

- [x] El preview de playlist y de canal lista las `Entry` sin descargar, con `truncated` si superan 500.
- [x] Las `Entry` disponibles vienen seleccionadas y se pueden deseleccionar; las no disponibles se muestran deshabilitadas con motivo.
- [x] Encolar crea un `Batch` y un job por `Entry` seleccionada; el servidor rechaza URLs que no sean de YouTube.
- [x] Los archivos se guardan en `DOWNLOAD_DIR/<folder_name>/<NN> - <título>.<ext>` (por defecto `~/Downloads`), con `NN` según la posición en la playlist.
- [x] `folder_name` es válido en macOS y Windows; descargar la misma playlist dos veces reutiliza la carpeta y resuelve colisiones por archivo.
- [x] Los jobs de un batch son independientes entre sí.
- [x] Se elimina el rechazo provisional `playlist_unsupported` del ticket 04 (marcado `TICKET-09` en el código).
- [x] Tests unitarios de saneado y numeración, y tests de integración con `FakeEngine` para preview y descarga de playlists.

## Comments

**2026-11-15 — Implementación.**

- **Canales**: grabado contra YouTube real con el `yt-dlp` 2026.10.26. La raíz de un canal con varias pestañas (`@Fireship`) devuelve solo pestañas como playlists anidadas (`Videos`, `Live`, `Shorts`); un canal con una sola pestaña (`@jawed`) ya se resuelve a sus videos. El clasificador normaliza una URL de canal sin pestaña, o con una que no lista videos (`featured`, `playlists`, `community`...), a `/videos`; se conservan `videos`, `shorts`, `streams` y `live`. Si aun así llegan playlists anidadas, el preview falla con `preview_failed`. Fixtures en `backend/tests/fixtures/ytdlp/` (`playlist`, `playlist_unavailable`, `channel_tabs`, `channel_videos`, `channel_single`), recortadas. El preview de playlist usa 3 veces el tiempo límite del de video (90 s).
- **No disponibles**: en la playlist real `PL59FEE129ADFF2B12` yt-dlp no entrega `[Private video]` ni `availability`: las `Entry` privadas o eliminadas llegan sin `title` ni `duration`. Se trata ese caso como "Video privado o eliminado"; además se reconocen los títulos `[Private video]`/`[Deleted video]`, `availability` (`private`, `needs_auth`, `subscriber_only`, `premium_only`) y `live_status` de directo o estreno. Su título visible es "Video no disponible".
- **`truncated`**: `playlist_count > 500`; si yt-dlp no lo trae (canales), una página llena de 500. Con exactamente 500 videos y sin conteo el aviso aparece aunque no falte ninguno.
- **Encolar**: `POST /api/jobs` con una URL de playlist exige `entries` (`422 no_entries` si falta o está vacío), valida cada URL con el clasificador (`422 invalid_entry`, y no se crea nada), rechaza índices repetidos (`invalid_entries`) y más de 500. Un video suelto con `entries` da `invalid_entries`. Misma validación de opciones que un video. El `Batch` guarda `title` (el del cliente, o "Playlist"), `folder_name` y `entry_count` = número de jobs.
- **Archivos**: `jobs/folders.py` (saneado, relleno, nombre numerado) y `FileMover.move(source, subdir, name)`. El relleno es `max(2, dígitos de max(entry_count, mayor playlist_index del batch))`: si se eligen pocas `Entry` de una playlist larga (p. ej. la 3 y la 120), `entry_count` solo no basta para que el orden alfabético respete la playlist.
- **Desviación (API)**: cada job incluye `batchTitle` y `batchEntryCount` (join con `batches`). La spec no lista un endpoint de batches y la UI necesita el título del grupo también tras recargar o por SSE. Códigos nuevos `no_entries`, `invalid_entry`, `invalid_entries`; `playlist_unsupported` eliminado.
- **UI**: el preview de playlist muestra título, autor, cantidad, aviso de truncado, lista con casillas (las disponibles marcadas; las demás deshabilitadas con motivo), "Seleccionar todo"/"Ninguno", contador, todas las calidades y presets, y "Descargar N videos". La lista de descargas agrupa los jobs de un batch bajo su título con "3/10 completadas" (más "en curso" y "con error"), en la posición de su job más reciente; los jobs siguen siendo tarjetas individuales. La rehidratación pide 200 jobs, así que un batch muy grande puede verse incompleto tras recargar hasta que ticket 11 pagine el historial.
- **Verificación**: pytest, ruff (check y format), Vitest y build en verde. Real con `docker compose up --build` (`HOST_DOWNLOAD_DIR=.dev-data/downloads`): preview de la playlist `PLrAXtm...` (2 videos), de `@Fireship` (normalizado a `/videos`, 500 `Entry`, `truncated: true`) y de `PL59FEE...` (3 no disponibles con motivo); un batch de 2 videos en m4a con título `Select: Lectures?` dejó `Select Lectures/01 - Me at the zoo.m4a` y `02 - ….m4a`, y encolarlo otra vez reutilizó la carpeta con ` (2)`. Medios de prueba borrados. La UI solo se probó con tests de componente (no en navegador).
