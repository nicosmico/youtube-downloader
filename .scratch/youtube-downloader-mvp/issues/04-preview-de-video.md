# 04: Preview de video

**What to build:** Al pegar una URL, la app la clasifica (video, playlist, mix, otro sitio) antes de invocar `yt-dlp`. Para un video, la UI muestra automáticamente un `MediaPreview` con título, miniatura, duración, autor y las calidades realmente disponibles, deshabilitando las `Quality` superiores a la máxima. Si la URL de video venía de una lista, ofrece "ver playlist completa". Los errores de sitio no soportado, mix, directo o estreno, contenido no público, video no disponible, URL inválida y timeout se muestran con mensajes claros. El preview no descarga ni crea jobs.

**Blocked by:** 03 (Engine Manager).

**Status:** ready-for-agent

- [x] Una URL de video público muestra metadatos y calidades coherentes.
- [x] `watch?v=…&list=…` se trata como video e incluye `playlistUrl`.
- [x] Una URL que no es de YouTube se rechaza con `unsupported_site` sin invocar `yt-dlp`.
- [x] Un mix (`list=RD…`) se rechaza con `mix_playlist`; un directo o estreno, con `live_content`.
- [x] Una URL privada o restringida muestra un mensaje claro de contenido no público.
- [x] Una URL inválida y un timeout se manejan sin bloquear la API.
- [x] El preview no crea archivos ni `DownloadJob`.
- [x] La UI muestra estados de carga y error.
- [x] Con el Engine sin `ready`, la API responde `engine_not_ready` y la UI deshabilita el campo de URL (usa `engineReady`).
- [x] Tests unitarios del clasificador de URLs y tests de integración con `FakeEngine`, sin red.

## Comments

**2026-11-15**: implementado en la rama `ticket/04-preview` (sin push).

Qué hay:
- `backend/app/preview/`: `urls.py` (clasificador puro: `ClassifiedUrl{kind, url normalizada, playlist_url}` o `UrlRejected(code)`), `mapping.py` (`-J` → `MediaPreview`), `failures.py` (stderr de yt-dlp → código y mensaje en español saneado), `service.py` (`PreviewService`: clasifica, corre yt-dlp, mapea). `engine/commands.py` (`ytdlp_base_args`: binario + `--ffmpeg-location` + `--js-runtimes deno:<ruta>`, reutilizable por los tickets 05 y 09).
- `engine/io.py`: `Runner` ahora acepta `timeout`; `run_process` usa `Popen` con grupo de procesos propio y mata el árbol al vencer (`ProcessTimeout`); `ProcessError.stderr` conserva el stderr completo (nunca se muestra).
- `POST /api/preview` (ruta `def`, corre en el threadpool: la API no se bloquea) detrás de `require_engine_ready`. `create_app(ytdlp_runner=...)` es el borde de subprocess que sustituye el `FakeYtdlp` en tests.
- Playlists y canales: 422 `playlist_unsupported` temporal (marcado `TICKET-09` en `service.py`; el mensaje y el texto de la UI son lo único más que se borra).
- UI: `app-url-preview` (campo, debounce 500 ms, inmediato al pegar, `switchMap` que cancela la petición anterior, tarjeta con miniatura/título/autor/duración/selector de calidades con las superiores deshabilitadas, aviso de VLC en 2160p, "Ver playlist completa", mensajes por código) y `PreviewService`. El campo se deshabilita con `engineReady` en falso. No hay botón de encolar (ticket 05); la calidad elegida queda en `UrlPreview.quality`.

Reglas decididas:
- `availableQualities`: `best` siempre, más cada tope (`2160p`, `1080p`, `720p`, `480p`) menor o igual que el lado menor máximo del video (un tope superior bajaría el mismo archivo que `best`). 1440p ofrece best/1080p/720p/480p; por debajo de 480 solo `best`. `maxQuality` es el mayor tope disponible (o `best`). Se añade `maxResolution` (lado menor, entero) a `MediaPreview` para mostrarlo; no está en la spec.
- `live_status`: se aceptan `None`, `not_live` y `was_live`; todo lo demás (`is_live`, `is_upcoming`, `post_live`, valores nuevos) es `live_content`. `post_live` se rechaza porque la grabación aún se procesa y sus formatos no son fiables.
- Códigos HTTP: 422 para los rechazos de contenido (incl. `unavailable`, `not_public`), 504 `timeout`, 502 `preview_failed` (genérico, nuevo), 409 `engine_not_ready`. El bot-check de YouTube ("not a bot", 429) va a `preview_failed`, no a `not_public`.

Hallazgo de spec: un estreno pendiente no devuelve JSON con `live_status: is_upcoming`; `yt-dlp -J` falla con `ERROR: ... This live event will begin in N minutes.`, y también un directo terminado sin grabación ("This live stream recording is not available."). Se mapean por stderr a `live_content`; el criterio de `live_status` de la spec solo cubre los directos en curso.

Tests: fixtures reales grabadas con red y recortadas en `backend/tests/fixtures/ytdlp/` (video normal, Short vertical, 4K, directo). Estrenos, edad y no disponible se grabaron como stderr; los de privado, miembros y geobloqueo son los textos del extractor de yt-dlp, no capturados (no se encontró un video privado real). Clasificador con tabla, mapeo, errores, API con `FakeYtdlp` (flags exactos, timeout con un falso colgado mientras `/api/health` responde, sin archivos nuevos), `run_process` real con un hijo colgado (se mata el árbol) y un test `network` (`pytest -m network tests/test_preview_network.py`; con `ENGINE_BIN_DIR` reutiliza un Engine instalado). Frontend: 87 tests (carga, éxito, cada error, deshabilitado sin Engine, cancelación de peticiones obsoletas).

Verificación: pytest 313 (+ network OK con el Engine de `.dev-data`), ruff check/format, Vitest 87 y build OK. Con `docker compose up --build` y `curl` real (el preview tarda ~2 s): video con `list=` → `playlistUrl`; Short vertical → `["best","1080p","720p","480p"]`; 4K → las cinco; vimeo → `unsupported_site` (1 ms, sin yt-dlp); mix → `mix_playlist`; directo → `live_content`; edad → `not_public`; id inexistente → `unavailable`; canal → `playlist_unsupported`. No se probó la UI en un navegador real, solo con tests de componente.

Ejemplo (Short, recortado):

```json
{"kind":"video","id":"Jt5fgKBqZSY","url":"https://www.youtube.com/watch?v=Jt5fgKBqZSY","title":"ok so lunch is hitting harder than ever imagined…","thumbnail":"https://i.ytimg.com/vi/Jt5fgKBqZSY/maxresdefault.jpg","duration":32,"author":"YouTube","availableQualities":["best","1080p","720p","480p"],"maxQuality":"1080p","maxResolution":1080}
```

**2026-11-15 — Revisión del orquestador.** Checks repetidos (313 backend, 87 frontend, ruff, build). Probado en el navegador integrado con el Engine real: preview de "Me at the zoo" con `list=` (solo "Mejor disponible" por ser 240p), "Ver playlist completa" muestra el aviso provisional y una URL de Vimeo muestra "Solo se admiten enlaces de YouTube.". Spec actualizada con `maxResolution`, códigos HTTP del preview y reglas de calidades y `live_status`.
