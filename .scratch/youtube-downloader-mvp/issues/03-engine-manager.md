# 03: Engine Manager

**What to build:** En el primer arranque, la app descarga `yt-dlp`, `ffmpeg`, `ffprobe` y Deno en su directorio de datos, verifica su SHA-256 y sus versiones, y expone el estado `missing`, `installing`, `ready` o `error` por SSE. La UI muestra ese estado y bloquea el encolado hasta que el Engine esté listo. Incluye actualización de `yt-dlp` (manual, al arrancar si pasaron más de 24 h y cada 24 h mientras la app está abierta) por descarga, verificación e intercambio del binario, sin `-U` (ADR-0002). Las fuentes y la tabla de assets están en la spec, validadas en el spike 01. `ENGINE_BIN_DIR` permite usar binarios montados en desarrollo. En el contenedor Linux se descargan binarios Linux; macOS arm64 y Windows x64 se resuelven por plataforma en producción.

**Blocked by:** 02 (Walking skeleton en Docker).

**Status:** ready-for-agent

- [x] Con el directorio de binarios vacío, la app descarga, verifica y activa los cuatro binarios dentro del contenedor Linux.
- [x] Un binario con hash incorrecto no se activa y deja el estado `error`.
- [x] Si Deno falta o `deno --version` falla, el Engine queda en `error`; no hay modo degradado.
- [x] Los restos `.old` y `.new` se borran al arrancar.
- [x] `ENGINE_BIN_DIR` permite apuntar a binarios montados sin cambiar el código.
- [x] `engine.json` registra versión y hash de cada binario y la fecha del último chequeo de `yt-dlp`.
- [ ] La UI muestra el estado y bloquea el encolado hasta `ready`.
- [x] Un fallo de red deja estado `error` con mensaje y opción de reintentar.
- [x] La actualización manual descarga el último release, lo verifica contra `SHA2-256SUMS`, intercambia el binario y cambia la versión y el hash en `engine.json` sin reiniciar la app.
- [x] La actualización no arranca mientras haya descargas activas (la coordinación con la `Queue` se completa en el ticket 06).
- [x] El chequeo periódico corre cada 24 h con reloj inyectable.
- [x] El mapeo de assets y hashes para macOS arm64, Windows x64 y Linux arm64/x64 queda cubierto por tests unitarios, incluido el zip de Gyan con `bin/ffmpeg.exe` y `bin/ffprobe.exe`.
- [x] Tests con descargador y `FakeEngine` simulados, sin red.

## Comments

**2026-11-15**: implementado en la rama `ticket/03-engine-manager` (sin push).

Qué hay:
- `backend/app/engine/`: `sources.py` (versiones y SHA-256 fijados de Deno 2.9.8 y ffmpeg/ffprobe 9.0.2 para macOS arm64, Windows x64, Linux arm64/x64; yt-dlp dinámico contra `SHA2-256SUMS`), `io.py` (`Fetcher`/`Runner` inyectables), `manager.py` (`EngineManager`: `missing → installing → ready | error`, instalación por componente con reintento sin repetir descargas, actualización de yt-dlp por swap `.old`/`.new` con rollback, `engine.json`, `tick()` de 24 h, `can_update()` como gancho para la `Queue`, `ENGINE_BIN_DIR`), `guard.py` (`require_engine_ready`, 409 `engine_not_ready`).
- `backend/app/events.py`: `EventBroadcaster` (colas acotadas por cliente) y `GET /api/events` (snapshot `engine.updated` al conectar, cambios, heartbeat `: heartbeat` cada 15 s). Los tickets siguientes publican `job.*`/`queue.updated` por el mismo broadcaster.
- API: `GET /api/system/engine`, `POST /api/system/engine/install` (reintento; no está en la tabla de la spec), `POST /api/system/engine/update` (202, o 409 `engine_not_ready`/`engine_busy`/`engine_external`); `/api/health` devuelve el estado real.
- UI: tarjeta del Engine (No instalado / Instalando… / Listo con versiones y "Actualizar yt-dlp" / Error con "Reintentar"), en vivo por `EventSource` y rehidratada con `GET /api/system/engine` en cada (re)conexión. `EngineService.engineReady` queda para las pantallas de preview y encolado, que aún no existen: por eso el ítem "bloquea el encolado" sigue sin marcar.
- El uso de `can_update()` por la `Queue` (esperar jobs activos y no despachar durante la actualización) queda para el ticket 06.

Cómo correrlo:
- `docker compose up --build` con `./.dev-data/bin` vacío; `curl http://127.0.0.1:8765/api/system/engine` pasa de `installing` a `ready`; `./.dev-data/engine.json` guarda versión y hash.
- `docker compose run --rm tests` (sin red), `... tests ruff check .`, `... tests ruff format --check .`; `docker compose run --rm tests pytest -m network` instala el Engine real en un directorio temporal.
- `cd frontend && npm run test:ci && npm run build`.
- `ENGINE_BIN_DIR=<carpeta>` usa binarios existentes sin descargar (ver README).

Verificación: pytest 128 tests + 1 `network` (instala el Engine Linux arm64 real), ruff, Vitest 15 tests y build OK; en Compose se comprobó `deno`/`ffmpeg`/`ffprobe`/`yt-dlp --version` dentro del contenedor, reinicio sin volver a descargar y `docker compose down` con un stream SSE abierto (3 s, gracias a `timeout_graceful_shutdown`).
