# 01: macOS — reabrir la app mientras está abierta

**What to build:** En macOS empaquetado, el ejecutable del `.app` deja de ser el servidor: lanza el servidor como proceso hijo desacoplado (sesión nueva, fuera de LaunchServices) y termina enseguida. Así cada doble clic arranca un lanzador nuevo que pasa por `Single Instance` y abre una pestaña en la instancia existente, en vez del aviso de Finder "La aplicación YouTube Downloader ya no está abierta.". Desarrollo, Docker y Windows no cambian. Ver la sección "macOS: lanzador en segundo plano" de la spec.

**Blocked by:** None (can start immediately).

**Status:** ready-for-agent

- [ ] Con la app abierta, un doble clic en el `.app` abre una pestaña nueva en la instancia existente, sin avisos de Finder.
- [ ] Con la app cerrada, un doble clic la arranca y abre el navegador.
- [ ] El lanzador termina en segundos; el servidor sigue vivo tras cerrar la pestaña y respeta `Idle Shutdown` y "Cerrar aplicación".
- [ ] El hijo hereda `DATA_DIR`/`DOWNLOAD_DIR` y escribe `runtime.json` y `app.log` como hoy.
- [ ] El smoke de CI arranca el `.app` con `open` en `macos-latest` y comprueba que una segunda apertura reutiliza la instancia.
- [ ] Verificado a mano en un Mac real desde el zip del Release.
- [ ] README (sin icono en el Dock) y ADR-0001 actualizados.
