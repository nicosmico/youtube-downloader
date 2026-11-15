# 01: Spike — Engine y empaquetado

**What to build:** Validar las dos integraciones más frágiles antes de comprometer código de producción: obtener y ejecutar `yt-dlp`, `ffmpeg` y `ffprobe` por plataforma y arquitectura; y empaquetar un "hola mundo" de FastAPI + estáticos + subprocess con PyInstaller `onedir` que abra el navegador. Confirmar también las flags vigentes de `yt-dlp` que asume la spec. El entregable son hallazgos y una decisión de proveedor, no código de producción.

**Blocked by:** None (can start immediately).

**Status:** ready-for-agent

- [ ] `yt-dlp` se descarga desde el release oficial y ejecuta en macOS; se confirma el asset por plataforma.
- [ ] `ffmpeg` y `ffprobe` se descargan, ejecutan y reportan versión en macOS arm64.
- [ ] Se elige un proveedor de `ffmpeg` por plataforma y arquitectura, y se documenta la decisión.
- [ ] Se confirman `--progress-template`, `--print after_move`, `-U` y `--merge-output-format mp4` contra la versión vigente; cualquier ajuste queda documentado.
- [ ] Un PyInstaller `onedir` con FastAPI, estáticos y subprocess arranca y abre el navegador.
- [ ] Windows se valida en VM o máquina disponible; si no hay acceso, se documenta el bloqueo y el plan alternativo.
- [ ] Los hallazgos quedan registrados y no sobrevive código de producción del spike.
