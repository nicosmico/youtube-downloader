# 03: Engine Manager

**What to build:** En el primer arranque, la app descarga `yt-dlp`, `ffmpeg` y `ffprobe` en su directorio de datos, verifica sus versiones y expone el estado `missing`, `installing`, `ready` o `error` por SSE. La UI muestra ese estado y bloquea el encolado hasta que el Engine esté listo. Incluye actualización manual y chequeo automático de `yt-dlp` cada 24 horas.

**Blocked by:** 02 (Walking skeleton).

**Status:** ready-for-agent

- [ ] Con el directorio de binarios vacío, la app descarga y verifica el Engine.
- [ ] La UI muestra el estado y bloquea el encolado hasta `ready`.
- [ ] Un fallo de red deja estado `error` con mensaje y opción de reintentar.
- [ ] La actualización manual cambia la versión reportada sin reiniciar la app.
- [ ] La actualización no interrumpe jobs activos.
- [ ] Tests con descargador y `FakeEngine` simulados, sin red.
