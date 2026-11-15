# 01: Spike — Engine, Docker y empaquetado

**What to build:** Validar las integraciones más frágiles antes de comprometer código de producción: obtener, verificar y ejecutar `yt-dlp`, `ffmpeg`, `ffprobe` y Deno en el contenedor Linux y confirmar los assets de macOS arm64 y Windows x64; confirmar las flags vigentes de `yt-dlp` que asume la spec; levantar un FastAPI "hola mundo" con estáticos en Docker Compose accesible desde el navegador del host; y construir un PyInstaller "hola mundo" en GitHub Actions con matriz macOS/Windows, verificando que el artefacto arranca. El entregable son hallazgos y decisiones, no código de producción.

**Blocked by:** None (can start immediately).

**Status:** resolved

- [x] `yt-dlp`, `ffmpeg`, `ffprobe` y Deno se descargan, verifican por SHA-256 y reportan versión en el contenedor Linux.
- [x] Se confirman los assets y la fuente de hashes de cada binario para macOS arm64 y Windows x64.
- [x] Se elige un proveedor de `ffmpeg` por plataforma y se documenta la decisión.
- [x] Se confirma la flag con la que `yt-dlp` recibe la ruta de Deno y que, con ella, un video de YouTube lista formatos completos.
- [x] Se confirma que `--progress` mantiene las líneas `PROGRESS` junto a `--print after_move:filepath`.
- [x] Se fija la fórmula `-S` por `Quality` (ADR-0009): prefiere H.264/AAC a igual resolución, cae a VP9/AV1 en 2160p y respeta el tope en videos verticales.
- [x] Se confirma `--merge-output-format mp4` sin recodificar y que `m4a` y `opus` se obtienen sin recodificar.
- [x] Se comprueba `yt-dlp -U` en Windows mientras otro `yt-dlp.exe` está en uso, o se documenta la alternativa.
- [x] Un "hola mundo" de FastAPI con estáticos corre en Docker Compose (`BIND_HOST=0.0.0.0`, `PORT` fijo) y es accesible desde el navegador del host en `127.0.0.1` con `OPEN_BROWSER=0`.
- [x] GitHub Actions en `macos-latest` produce un PyInstaller `onedir` arm64 que arranca y responde `/api/health`.
- [x] GitHub Actions en `windows-latest` produce un `.exe` sin consola que arranca y responde `/api/health`, o se documenta el bloqueo.
- [x] Los hallazgos quedan registrados en la spec o en un ADR, y no sobrevive código de producción del spike.

## Comments

**2026-11-15 — Resuelto.** Ejecutado por un subagente en la rama `spike/01` (código desechable en `spike/`, solo en esa rama). Builds de PyInstaller verificados en GitHub Actions (run `43748951815`) para macOS arm64 y Windows x64 sin consola. Hallazgos completos en `../spike-01-findings.md`.

Decisiones derivadas, ya incorporadas a la spec y a los ADR-0002 y ADR-0009:

- `--js-runtimes deno:<ruta>` y `--ffmpeg-location` en todas las invocaciones.
- Tabla `-S` por `Quality` y `-f` de audio sin recodificar para `m4a` y `opus`.
- Progreso por stdout (`PROGRESS`) y postproceso por stderr (`POSTPROC`).
- `ffmpeg`: martin-riedl en macOS y Linux, Gyan en Windows.
- Actualización de `yt-dlp` por intercambio propio con la `Queue` en pausa, sin `-U`.
- Deno obligatorio: si falla, el Engine queda en `error`.
