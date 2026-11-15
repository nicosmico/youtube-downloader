# 03: Engine Manager

**What to build:** En el primer arranque, la app descarga `yt-dlp`, `ffmpeg`, `ffprobe` y Deno en su directorio de datos, verifica su SHA-256 y sus versiones, y expone el estado `missing`, `installing`, `ready` o `error` por SSE. La UI muestra ese estado y bloquea el encolado hasta que el Engine esté listo. Incluye actualización de `yt-dlp` (manual, al arrancar si pasaron más de 24 h y cada 24 h mientras la app está abierta) por descarga, verificación e intercambio del binario, sin `-U` (ADR-0002). Las fuentes y la tabla de assets están en la spec, validadas en el spike 01. `ENGINE_BIN_DIR` permite usar binarios montados en desarrollo. En el contenedor Linux se descargan binarios Linux; macOS arm64 y Windows x64 se resuelven por plataforma en producción.

**Blocked by:** 02 (Walking skeleton en Docker).

**Status:** ready-for-agent

- [ ] Con el directorio de binarios vacío, la app descarga, verifica y activa los cuatro binarios dentro del contenedor Linux.
- [ ] Un binario con hash incorrecto no se activa y deja el estado `error`.
- [ ] Si Deno falta o `deno --version` falla, el Engine queda en `error`; no hay modo degradado.
- [ ] Los restos `.old` y `.new` se borran al arrancar.
- [ ] `ENGINE_BIN_DIR` permite apuntar a binarios montados sin cambiar el código.
- [ ] `engine.json` registra versión y hash de cada binario y la fecha del último chequeo de `yt-dlp`.
- [ ] La UI muestra el estado y bloquea el encolado hasta `ready`.
- [ ] Un fallo de red deja estado `error` con mensaje y opción de reintentar.
- [ ] La actualización manual descarga el último release, lo verifica contra `SHA2-256SUMS`, intercambia el binario y cambia la versión y el hash en `engine.json` sin reiniciar la app.
- [ ] La actualización no arranca mientras haya descargas activas (la coordinación con la `Queue` se completa en el ticket 06).
- [ ] El chequeo periódico corre cada 24 h con reloj inyectable.
- [ ] El mapeo de assets y hashes para macOS arm64, Windows x64 y Linux arm64/x64 queda cubierto por tests unitarios, incluido el zip de Gyan con `bin/ffmpeg.exe` y `bin/ffprobe.exe`.
- [ ] Tests con descargador y `FakeEngine` simulados, sin red.
