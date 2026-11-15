---
status: accepted
---

# `yt-dlp` y `ffmpeg` viven fuera del ejecutable

YouTube cambia con frecuencia y un `yt-dlp` congelado dentro del binario deja de funcionar en semanas. Decidimos que el ejecutable no empaquete el `Engine`: en el primer arranque descarga `yt-dlp`, `ffmpeg` y `ffprobe` en `~/.youtube-downloader/bin`, y actualiza `yt-dlp` con `-U` (al iniciar o por acción del usuario).

## Consequences

- El primer arranque requiere red y puede fallar; la UI debe mostrar el estado "preparando motor" con opción de reintentar.
- El ejecutable queda liviano y el motor se actualiza sin recompilar la app.
- Hay que resolver y validar la fuente de binarios por plataforma y arquitectura (macOS arm64/x86_64, Windows x64).
