# 01: Spike — Engine, Docker y empaquetado

**What to build:** Validar las integraciones más frágiles antes de comprometer código de producción: obtener y ejecutar `yt-dlp`, `ffmpeg` y `ffprobe` en el contenedor Linux y confirmar los assets de macOS; confirmar las flags vigentes de `yt-dlp` que asume la spec; levantar un FastAPI "hola mundo" con estáticos en Docker Compose accesible desde el navegador del host; y construir un PyInstaller "hola mundo" en GitHub Actions con matriz macOS/Windows, verificando que el artefacto arranca. El entregable son hallazgos y decisiones, no código de producción.

**Blocked by:** None (can start immediately).

**Status:** ready-for-agent

- [ ] `yt-dlp` se descarga y ejecuta en el contenedor Linux; se confirma el asset para macOS.
- [ ] `ffmpeg` y `ffprobe` se descargan, ejecutan y reportan versión en el contenedor Linux.
- [ ] Se elige un proveedor de `ffmpeg` por plataforma y arquitectura, y se documenta la decisión.
- [ ] Se confirman `--progress-template`, `--print after_move`, `-U` y `--merge-output-format mp4` contra la versión vigente; cualquier ajuste queda documentado.
- [ ] Un "hola mundo" de FastAPI con estáticos corre en Docker Compose y es accesible desde el navegador del host con `OPEN_BROWSER=0`.
- [ ] GitHub Actions en `macos-latest` produce un PyInstaller `onedir` que arranca y responde `/api/health`.
- [ ] GitHub Actions en `windows-latest` produce un `.exe` que arranca y responde `/api/health`, o se documenta el bloqueo.
- [ ] Los hallazgos quedan registrados y no sobrevive código de producción del spike.
