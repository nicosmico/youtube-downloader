# 02: Versión en el engranaje y aviso de versión nueva

**What to build:**

*Backend:* al arrancar, una comprobación en segundo plano y de una sola vez del último Release de la app:
- Pide `https://github.com/nicosmico/youtube-downloader/releases/latest` con `Fetcher.redirect_location` y parsea el tag `vX.Y.Z`.
- Si la versión publicada es mayor que `__version__`, expone `update: {version, url}` en `/api/health` (`null` si no hay) y publica el evento SSE `app.update` con ese mismo objeto.
- Si falla, lo registra en el log y no muestra nada.
- Se desactiva con `UPDATE_CHECK=0`.

*Frontend:*
- La línea `Versión X.Y.Z` al final del menú del engranaje.
- Si hay `update`, un chip-enlace en la barra superior junto al indicador del motor: flecha hacia arriba + `vX.Y.Z`, que abre `url` en una pestaña nueva. Bajo 640 px solo el icono. `aria-label`/`title`: "Hay una versión nueva: X.Y.Z".
- El chip se actualiza al recibir `app.update`.

Ver la spec, secciones "Versión en el engranaje" y "Aviso de versión nueva", y el ADR-0011.

**Blocked by:** None (can start immediately).

**Status:** ready-for-agent

- [x] La comprobación no bloquea el arranque ni el Engine. Con la red caída, no muestra nada y no deja errores visibles.
- [x] La comparación de versiones es numérica (`0.10.0` > `0.9.0`) y solo avisa si la publicada es estrictamente mayor.
- [x] La `url` se construye a partir del tag parseado, nunca copiando la `Location`.
- [x] `/api/health` incluye `update`, y el evento `app.update` llega a las pestañas abiertas.
- [x] `UPDATE_CHECK=0` no hace ninguna petición. Los tests del backend no tocan la red.
- [x] El menú del engranaje muestra la versión instalada.
- [x] El chip aparece solo con `update`, con contraste AA y foco visible en ambos temas, y sin saltos de línea a 320 px.
- [x] Tests de backend (versión, parseo, checker con `Fetcher` falso, health, evento, desactivado) y de frontend (chip, SSE, línea de versión).

## Comments

2026-11-16: Implementado.
- Backend: `backend/app/updates.py` (`parse_latest_version`, `is_newer`, `UpdateNotice`). `create_app` gana `update_check` (por defecto `False`, así los tests no tocan la red), `update_fetcher`, `app_version` y `spawn_update_check`; el Launcher pasa `Settings.update_check` (`UPDATE_CHECK=0` lo desactiva, activo por defecto). La comprobación corre en un hilo daemon desde el lifespan. `/api/health` incluye `update`; evento SSE `app.update`. El `UrllibFetcher` real (mismo contexto SSL) solo se construye al ejecutar la comprobación.
- Frontend: señal `SystemService.update` (health + `app.update`), chip-enlace con `arrow-up` en la barra superior, línea `Versión X.Y.Z` al final del menú (un `<p>`, no menuitem). Nuevo icono `arrow-up` y textos en `texts.ts`.
- Desviación: la línea de versión solo se muestra cuando `/api/health` ya respondió. Sin `UPDATE_CHECK` en `compose.yaml` (activo por defecto también en Docker, como pide la spec).
- Verificado: `docker compose run --rm tests` (697 passed), ruff check y format OK; `npm run test:ci` (253 passed) y `npm run build` OK. No revisado visualmente (contraste/320 px): lo hace el orquestador.
