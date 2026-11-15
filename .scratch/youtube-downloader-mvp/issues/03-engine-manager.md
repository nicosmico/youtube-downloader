# 03: Engine Manager

**What to build:** En el primer arranque, la app descarga `yt-dlp`, `ffmpeg` y `ffprobe` en su directorio de datos, verifica sus versiones y expone el estado `missing`, `installing`, `ready` o `error` por SSE. La UI muestra ese estado y bloquea el encolado hasta que el Engine esté listo. Incluye actualización manual y chequeo automático de `yt-dlp` cada 24 horas. `ENGINE_BIN_DIR` permite usar binarios montados en desarrollo. En el contenedor Linux se descargan binarios Linux; macOS y Windows se resuelven por plataforma en producción.

**Blocked by:** 02 (Walking skeleton en Docker).

**Status:** ready-for-agent

- [ ] Con el directorio de binarios vacío, la app descarga y verifica el Engine dentro del contenedor Linux.
- [ ] `ENGINE_BIN_DIR` permite apuntar a binarios montados sin cambiar el código.
- [ ] La UI muestra el estado y bloquea el encolado hasta `ready`.
- [ ] Un fallo de red deja estado `error` con mensaje y opción de reintentar.
- [ ] La actualización manual cambia la versión reportada sin reiniciar la app.
- [ ] El mapeo de assets para macOS y Windows queda cubierto por tests unitarios.
- [ ] Tests con descargador y `FakeEngine` simulados, sin red.
