# 07: Opciones nivel 1

**What to build:** La UI permite elegir modo video con `Quality` `2160p`, `1080p`, `720p` o `480p`, o modo audio con `AudioFormat` `mp3`, `m4a` u `opus`. La API y la UI rechazan combinaciones inválidas. La descarga usa el orden de formatos acordado en el spike: a igual resolución prefiere H.264/AAC en `.mp4` (ADR-0009) y mide la `Quality` sobre el lado menor. El audio solo se recodifica cuando el formato pedido no existe de forma nativa. La UI indica junto a `2160p` que puede requerir un reproductor como VLC.

**Blocked by:** 06 (Cola persistente y concurrencia).

**Status:** resolved

- [x] Cada `Quality` produce un archivo cuyo lado menor es menor o igual al tope elegido, también en videos verticales.
- [x] A 1080p o menos, el archivo es H.264/AAC en `.mp4` cuando YouTube lo ofrece.
- [x] Cada `AudioFormat` produce un archivo reproducible en su formato; `m4a` y `opus` no se recodifican si existe el stream nativo.
- [x] La API rechaza `quality` en modo audio y `audioFormat` en modo video.
- [x] La UI impide enviar combinaciones inválidas y muestra el aviso de `2160p`.
- [x] Tests de contrato de los argumentos de `yt-dlp` por modo y calidad.
- [x] La selección se conserva al encolar.
- [x] Se elimina el rechazo provisional `audio_unsupported` del ticket 05 (marcado `TICKET-07` en el código).

## Comments

**2026-11-15 — Implementación.**

- **API** (`jobs/api.py`): `CreateJob` acepta `audioFormat` (`mp3|m4a|opus`). `_check_options` exige `quality` en video y `audioFormat` en audio y prohíbe el otro campo; si no, `422 invalid_options` con mensaje en español. Valores fuera de enum siguen siendo `validation_error`. Se eliminó `audio_unsupported` (backend y `texts.ts`).
- **Desviación menor**: en modo video `quality` ahora es obligatorio (antes por defecto `best`), según "requiere" del encargo; el test de "calidad por defecto" pasó a enviar `quality` explícito.
- **Argumentos** (`jobs/arguments.py`): audio añade `-f <selector> -x --audio-quality 0 --audio-format <fmt>` y nada de `-S`/`--merge-output-format`; video no cambia. `UnsupportedJob` solo queda como defensa ante modos/formatos desconocidos.
- **UI**: interruptor Video/Solo audio (radios), selector de calidad (opciones sobre `maxQuality` deshabilitadas, "(puede requerir VLC)" junto a 2160p y un aviso al elegirla) o selector de formato. Modo, calidad y formato se conservan al previsualizar otra URL (si el siguiente video no ofrece la calidad guardada, vuelve a `best`). Las tarjetas muestran "Video · 720p" / "Audio · MP3".
- **AudioFormat por defecto: `m4a`**: es el stream nativo de YouTube (AAC, itag 140), sin recodificar y reproducible en todas partes; `mp3` siempre recodifica y `opus` no abre en todos los reproductores.
- **Tests**: matriz de validación de la API, contratos de argumentos por calidad y formato, runner con `FakeEngine` emitiendo `FixupM4a`/`ExtractAudio`, Vitest de interruptor, opciones deshabilitadas, aviso 2160p, payloads, persistencia y etiquetas.
- **Verificación real** (`docker compose up`, `HOST_DOWNLOAD_DIR=.dev-data/downloads`, ffprobe del contenedor): `jNQXAC9IVRw` como mp3 (`mp3`, 48 kHz), m4a (`aac` LC, 127999 b/s = itag 140 nativo) y opus (`opus`, Ogg); `2PuFyjAs7JA` a 480p: `.mp4` h264 854x480 + aac. Una petición con `quality` y `audioFormat` a la vez devolvió `422 invalid_options`. Solo se probó 480p horizontal en real; el lado menor en verticales y 720p/1080p/2160p se apoyan en el spike 01 y en los tests de contrato. La UI solo se probó con tests de componente.

**2026-11-15 — Revisión del orquestador.** Checks repetidos (447 backend, 121 frontend, ruff, build). Probado en el navegador integrado: selector Video/Audio, `M4A (AAC, sin recodificar)` por defecto y descarga real completada como "Audio · M4A". Spec actualizada con `invalid_options` y el formato de audio por defecto.

**2026-11-15 — Resuelto.** CI `43764161693` y Native `43764161812` verdes.
