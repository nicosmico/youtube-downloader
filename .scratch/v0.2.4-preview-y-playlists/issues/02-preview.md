# 02: Preview — descargar la playlist del vídeo, "Ir a YouTube", no disponibles y limpiar al descargar

**What to build:** Cinco cambios en el preview (`frontend/src/app/preview/url-preview.{ts,html,spec.ts}`, `core/texts.ts`, `core/preview.service.ts`, y `backend/app/preview/playlists.py` para el punto 7). Hallazgos del usuario en un Mac real con la v0.2.3.

**Blocked by:** None.

**Status:** ready-for-agent

## 1. Vídeo que viene de una playlist: "Descargar 1" y "Descargar N"

Hoy, si el preview de un vídeo trae `playlistUrl`, se muestra "Ver playlist completa" (`url-preview.html`, ~línea 183) junto al botón "Descargar".

- En ese caso, en cuanto se muestra el preview del vídeo, el componente pide **en segundo plano** el preview de `playlistUrl` (el mismo `PreviewService` que usa "Ver playlist completa"; se cancela si cambia la URL o se cierra el preview, como cualquier petición vieja).
- Los botones de descarga pasan a ser dos:
  - **"Descargar 1"**: solo este vídeo (lo que hoy hace "Descargar").
  - **"Descargar N"**: todos los vídeos disponibles de la playlist, con el formato elegido. Mientras se carga la playlist, desactivado y con spinner, con el texto "Descargar playlist" o similar hasta conocer N. Pone en cola exactamente lo mismo que seleccionar todos en la vista de la playlist y pulsar descargar (`jobs.enqueue(playlistUrl, options, playlistTitle, entries)`).
  - Si la playlist falla (error, mix, sin vídeos disponibles) o tiene un solo vídeo, no se muestra "Descargar N" y el botón del vídeo dice "Descargar", como hoy.
- "Ver playlist completa" se mantiene. Si la playlist ya está cargada, puede reutilizarse esa respuesta en vez de volver a pedirla (opcional).
- El formato (modo, calidad, audio) es el que esté elegido en el preview del vídeo. Si la calidad elegida no es `best`, vale igual para la playlist (en playlists se ofrecen todas).

## 2. "Descargar N" sin "videos"

- `texts.playlist.downloadMany` → `'Descargar {n}'`; `downloadOne` → `'Descargar 1'`. Un vídeo suelto sin playlist sigue diciendo "Descargar".

## 3. Botón "Ir a YouTube"

- En la fila del campo de la URL, después de "Pegar" (o en su hueco cuando "Pegar" no se muestra, Safari/Firefox). Botón secundario, mismo estilo que "Pegar", con un icono de enlace externo (añadir a `ui/icon.ts` si no existe, mismo estilo que los demás iconos).
- Es un `<a href="https://www.youtube.com/" target="_blank" rel="noopener noreferrer">`. En pantallas estrechas pasa a la línea de abajo (la fila puede hacer `flex-wrap`).

## 4. Vídeos no disponibles fuera de la selección

- `backend/app/preview/playlists.py`: `to_playlist_preview` deja fuera las entradas con `available: false`. Cada entrada conserva su `index` original (es la posición en la playlist y numera los archivos). `entryCount` es el número de entradas devueltas.
- Si no queda ninguna, `PreviewFailure(failure("unavailable", "Esta playlist no tiene videos disponibles."))`.
- `truncated` sigue calculándose sobre la playlist completa, como hoy.
- Frontend: el código de filas en gris (`entry.available`, `unavailableReason`) puede quedarse por compatibilidad, pero ya no se usa; si se quita, quitarlo también de `PlaylistEntry` y sus tests. Decide lo más simple.
- Actualizar los tests de `backend/tests/test_preview_playlists.py` (la fixture real `playlist_unavailable.json` tiene tres entradas sin título).

## 5. Al poner en cola: limpiar

- Cuando `jobs.enqueue` termina bien (vídeo, "Descargar 1", "Descargar N" o la selección de una playlist), el campo de la URL se vacía, el preview se cierra (incluida la lista de la playlist) y el foco vuelve al campo. Lo que quede del estado `enqueued` (mensaje "Añadido…") se elimina si ya no tiene dónde mostrarse: la descarga aparece en el listado.
- Si falla, todo se queda como estaba y se muestra el error, como hoy.

## Acceptance criteria

- [x] Los cinco puntos, con tests en `url-preview.spec.ts` (Vitest + jsdom): playlist en segundo plano y "Descargar N" que pone en cola todas las entradas; sin "Descargar N" si la playlist falla o tiene 1 vídeo; textos nuevos; enlace a YouTube con `target=_blank` y `rel`; limpieza tras éxito y no tras error.
- [x] Tests de backend del punto 4.
- [x] `npm run test:ci` y `npm run build` en `frontend/`; `docker compose run --rm tests`, `ruff check .`, `ruff format --check .`.
- [x] Sin textos que expliquen la UI.

## Comments

- 2026-11-16: implementado. Backend: `to_playlist_preview` filtra las entradas no disponibles (conservan `index`) y falla con "Esta playlist no tiene videos disponibles." si no queda ninguna. Frontend: el preview de un vídeo con `playlistUrl` carga la playlist en segundo plano (`switchMap`, se cancela al cambiar o limpiar); "Descargar 1" (primario, `download-button`) y "Descargar N" (secundario, `download-all-button`, con spinner y "Descargar playlist" mientras carga; oculto si falla o hay <=1 vídeo, y entonces el botón dice "Descargar"). "Ir a YouTube" fuera del input, en una fila con `flex-wrap`. Tras encolar bien se llama a `clear()` (vacía, cierra y enfoca); se eliminó el estado `enqueued` y el texto `preview.enqueued`. Decisiones: "Ver playlist completa" vuelve a pedir la playlist (no reutiliza la respuesta); el código de filas en gris del frontend (`available`, `unavailableReason`) se deja por compatibilidad; mientras carga la playlist el botón del vídeo ya dice "Descargar 1".
