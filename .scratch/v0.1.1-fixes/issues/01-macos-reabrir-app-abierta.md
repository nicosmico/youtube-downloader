# 01: macOS — reabrir la app mientras está abierta

**What to build:** En macOS empaquetado, el ejecutable del `.app` deja de ser el servidor: lanza el servidor como proceso hijo desacoplado (sesión nueva, fuera de LaunchServices) y termina enseguida. Así cada doble clic arranca un lanzador nuevo que pasa por `Single Instance` y abre una pestaña en la instancia existente, en vez del aviso de Finder "La aplicación YouTube Downloader ya no está abierta.". Desarrollo, Docker y Windows no cambian. Ver la sección "macOS: lanzador en segundo plano" de la spec.

**Blocked by:** None (can start immediately).

**Status:** ready-for-agent

- [ ] Con la app abierta, un doble clic en el `.app` abre una pestaña nueva en la instancia existente, sin avisos de Finder.
- [x] Con la app cerrada, un doble clic la arranca y abre el navegador.
- [ ] El lanzador termina en segundos; el servidor sigue vivo tras cerrar la pestaña y respeta `Idle Shutdown` y "Cerrar aplicación".
- [x] El hijo hereda `DATA_DIR`/`DOWNLOAD_DIR` y escribe `runtime.json` y `app.log` como hoy.
- [x] El smoke de CI arranca el `.app` con `open` en `macos-latest` y comprueba que una segunda apertura reutiliza la instancia.
- [ ] Verificado a mano en un Mac real desde el zip del Release.
- [x] README (sin icono en el Dock) y ADR-0001 actualizados.

## Comments

2026-11-15: Implementado en `backend/app/detach.py` (decisión pura `should_detach` + `spawn_server_child` con spawner inyectable) y `packaging/entry.py`. Marca de entorno `YTDL_SERVER_CHILD=1` para que el hijo ejecute el Launcher de siempre. Pruebas unitarias en `backend/tests/test_detach.py`.

CI (run Native 43780483071, verde en macos-arm64 y windows-x64; CI 43780483079 verde): `packaging/smoke.py --reopen` arranca el `.app` con `open --env`, espera `runtime.json` y `/api/health`, comprueba que queda un único proceso (el servidor), vuelve a hacer `open`, espera "Reusing instance" en `app.log`, comprueba que `runtime.json` no cambia y que sigue un solo proceso, apaga por API y verifica que el proceso desaparece. El smoke del ejecutable interno sigue, ahora con `YTDL_SERVER_CHILD=1` para no desacoplarse.

Sin marcar (a mano en un Mac real desde el zip del Release): doble clic con la app abierta sin aviso de Finder; el servidor sigue vivo tras cerrar la pestaña y respeta `Idle Shutdown` y "Cerrar aplicación" (la parte de `Idle Shutdown` no cambia respecto a v0.1.0, pero no se probó con el `.app` desacoplado).

**2026-11-15 — Publicado en `v0.1.1`** (Native/Release `43782090965`). Pendiente la verificación a mano en un Mac real desde el zip del Release.
