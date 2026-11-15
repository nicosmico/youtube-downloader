# 02: Walking skeleton en Docker

**What to build:** El esqueleto ejecutable del producto corriendo en Docker Compose: FastAPI sirve el shell de Angular (en español), expone `/api/health`, aplica `Single Instance`, apagado ordenado y validaciones de seguridad. El host abre el navegador en el puerto publicado. GitHub Actions ejecuta la suite con la misma imagen. Todavía no hay binario nativo; eso llega en los tickets de empaquetado.

**Blocked by:** 01 (Spike — Engine, Docker y empaquetado).

**Status:** ready-for-agent

- [x] `docker compose up` levanta el backend y sirve el shell de Angular en el puerto publicado solo en `127.0.0.1` del host.
- [x] `BIND_HOST` y `PORT` solo se usan en desarrollo; sin ellos el `Launcher` hace bind a `127.0.0.1:0`.
- [ ] El host abre el navegador y ve el shell; el contenedor corre con `OPEN_BROWSER=0`.
- [x] `/api/health` responde identificador y versión de la app, estado del Engine y puerto.
- [x] Un lock de archivo impide dos arranques simultáneos; una segunda instancia reutiliza la existente o se documenta el comportamiento en Compose.
- [x] "Cerrar aplicación" apaga el servidor y limpia `runtime.json`.
- [x] Peticiones con `Host` no local o mutaciones sin la cabecera de la app son rechazadas.
- [x] Python 3.13 con `uv`, `ruff` y `pytest` configurados en el contenedor.
- [ ] GitHub Actions corre lint y tests en el mismo contenedor y queda verde.
- [x] Los tests corren sin Python instalado en el host.

## Comments

**2026-11-15**: implementado en la rama `ticket/02-walking-skeleton` (sin push).

Qué hay:
- `backend/` (FastAPI, `uv.lock`, ruff, pytest), `frontend/` (Angular 22, standalone + signals, Vitest + jsdom), `compose.yaml`, `backend/Dockerfile` multi-stage (targets `backend` para tests y `app` para servir), `.github/workflows/ci.yml`.
- `Launcher` (`python -m app`): bind a `127.0.0.1:0` por defecto (o `BIND_HOST`/`PORT`), `runtime.json`, lock `instance.lock`, logs en `$DATA_DIR/app.log`, `--no-browser`/`OPEN_BROWSER=0`. SIGINT/SIGTERM y `POST /api/system/shutdown` cierran ordenadamente y borran `runtime.json`.
- Seguridad en middleware ASGI: Host (403 `invalid_host`), cabecera `X-Requested-With` y `Origin` en mutaciones (403).
- Shell en español con estado del Engine (`missing`, placeholder) y "Cerrar aplicación".

Cómo correrlo (ver README, sección Desarrollo):
- `docker compose up --build` y abrir `http://127.0.0.1:8765/`.
- `docker compose run --rm tests` (pytest), `... tests ruff check .`, `... tests ruff format --check .`.
- `cd frontend && npm ci && npm run test:ci && npm run build`.

Verificado localmente: health, SPA y fallback, LAN IP rechazada (conexión rechazada), 403 sin cabecera / Host malo / Origin malo, shutdown y `docker compose stop` salen con código 0 y limpian `runtime.json`; Single Instance (reuse, stale tras `kill -9`) dentro del contenedor; proxy de `ng serve`; 47 tests backend + 5 frontend, ruff limpio.

Sin verificar:
- "El host abre el navegador": el navegador integrado denegó la navegación, solo se comprobó con curl; la apertura real (`webbrowser.open`) solo corre fuera de Docker.
- GitHub Actions no se ejecutó (sin push); los pasos del CI se reprodujeron con los mismos comandos en local.

Comportamiento en Compose: un segundo contenedor con el mismo directorio de datos falla con "Another instance is starting or stuck" (el lock sí se comparte por el bind mount, pero cada contenedor tiene su red y no alcanza el puerto del otro). Documentado en el README.
