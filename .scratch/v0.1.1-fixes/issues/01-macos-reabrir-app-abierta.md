# 01: macOS — reabrir la app mientras está abierta

**Status:** ready-for-agent

**Blocked by:** None (can start immediately).

**Qué pasa:** con la app en marcha (tras cerrar la pestaña del navegador), un doble clic en `YouTube Downloader.app` muestra el aviso de Finder "La aplicación YouTube Downloader ya no está abierta." y no abre ninguna pestaña. El servidor sigue vivo (`runtime.json` y `app.log` lo confirman).

**Causa:** LaunchServices permite una sola instancia por bundle. Al reabrir, no lanza un segundo proceso: pide al proceso existente que se active. El servidor Python no es una app Cocoa y no responde, así que Finder concluye que no está abierta. La lógica de `Single Instance` (que abre una pestaña en la instancia existente) nunca llega a ejecutarse en macOS. En Windows no ocurre.

**Decisión (2026-11-15):** opción 1, lanzador en segundo plano. Al arrancar desde el bundle en macOS, el ejecutable lanza el servidor como proceso hijo desacoplado (sesión nueva, fuera de LaunchServices) y termina enseguida. Cada doble clic arranca un lanzador nuevo que pasa por `Single Instance`. Se descartó una app Cocoa con PyObjC (icono en el Dock, "Salir" desde el Dock) por coste y riesgo. Actualizar el ADR-0001 con esta consecuencia.

**What to build:** el lanzador desacoplado solo en macOS empaquetado; en desarrollo, Docker y Windows el comportamiento no cambia. El hijo hereda `DATA_DIR`/`DOWNLOAD_DIR`, escribe `runtime.json` y abre el navegador como hoy. El README deja de decir que el icono aparece en el Dock.

- [ ] Con la app abierta, un doble clic en el `.app` abre una pestaña nueva en la instancia existente, sin avisos de Finder.
- [ ] Con la app cerrada, un doble clic la arranca y abre el navegador.
- [ ] El lanzador termina en segundos; el servidor sigue vivo tras cerrar la pestaña y respeta `Idle Shutdown` y "Cerrar aplicación".
- [ ] El smoke de CI arranca el `.app` por el mismo camino (lanzador) y lo valida en `macos-latest`.
- [ ] Verificado a mano en un Mac real desde el zip del Release.
- [ ] README y ADR-0001 actualizados.
