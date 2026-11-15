# 01: Spike — Engine, Docker y empaquetado

**What to build:** Validar las integraciones más frágiles antes de comprometer código de producción: obtener, verificar y ejecutar `yt-dlp`, `ffmpeg`, `ffprobe` y Deno en el contenedor Linux y confirmar los assets de macOS arm64 y Windows x64; confirmar las flags vigentes de `yt-dlp` que asume la spec; levantar un FastAPI "hola mundo" con estáticos en Docker Compose accesible desde el navegador del host; y construir un PyInstaller "hola mundo" en GitHub Actions con matriz macOS/Windows, verificando que el artefacto arranca. El entregable son hallazgos y decisiones, no código de producción.

**Blocked by:** None (can start immediately).

**Status:** ready-for-agent

- [ ] `yt-dlp`, `ffmpeg`, `ffprobe` y Deno se descargan, verifican por SHA-256 y reportan versión en el contenedor Linux.
- [ ] Se confirman los assets y la fuente de hashes de cada binario para macOS arm64 y Windows x64.
- [ ] Se elige un proveedor de `ffmpeg` por plataforma y se documenta la decisión.
- [ ] Se confirma la flag con la que `yt-dlp` recibe la ruta de Deno y que, con ella, un video de YouTube lista formatos completos.
- [ ] Se confirma que `--progress` mantiene las líneas `PROGRESS` junto a `--print after_move:filepath`.
- [ ] Se fija la fórmula `-S` por `Quality` (ADR-0009): prefiere H.264/AAC a igual resolución, cae a VP9/AV1 en 2160p y respeta el tope en videos verticales.
- [ ] Se confirma `--merge-output-format mp4` sin recodificar y que `m4a` y `opus` se obtienen sin recodificar.
- [ ] Se comprueba `yt-dlp -U` en Windows mientras otro `yt-dlp.exe` está en uso, o se documenta la alternativa.
- [ ] Un "hola mundo" de FastAPI con estáticos corre en Docker Compose (`BIND_HOST=0.0.0.0`, `PORT` fijo) y es accesible desde el navegador del host en `127.0.0.1` con `OPEN_BROWSER=0`.
- [ ] GitHub Actions en `macos-latest` produce un PyInstaller `onedir` arm64 que arranca y responde `/api/health`.
- [ ] GitHub Actions en `windows-latest` produce un `.exe` sin consola que arranca y responde `/api/health`, o se documenta el bloqueo.
- [ ] Los hallazgos quedan registrados en la spec o en un ADR, y no sobrevive código de producción del spike.
