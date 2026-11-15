# 13: Empaquetado Windows

**What to build:** Completar el build de Windows iniciado en el ticket 14: `onedir` x64 con PyInstaller sin consola, build de Angular incluido, ícono, y publicación del `.zip` en un GitHub Release al crear un tag `v*`. El `.exe` debe funcionar en Windows 10/11 x64 sin Python, Node ni `ffmpeg` instalados. No se compila en el Mac del desarrollador.

**Blocked by:** 11 (Historial, multi-pestaña e Idle Shutdown), 14 (Smoke de empaquetado nativo).

**Status:** ready-for-agent

- [ ] Un tag `v*` publica el `.zip` en un GitHub Release; los PR producen solo artefactos de prueba.
- [ ] El `.exe` descargado arranca en Windows 10/11 x64 sin Python, Node ni `ffmpeg` instalados y sin ventana de consola.
- [ ] Prepara el Engine en el primer arranque y descarga un video y una playlist.
- [ ] Ningún subproceso abre ventanas de consola (`CREATE_NO_WINDOW`).
- [ ] `Single Instance`, "abrir carpeta" y "mostrar archivo" en Explorer, `Idle Shutdown` y el apagado ordenado funcionan desde el bundle.
- [ ] Cancelar no deja procesos huérfanos.
- [x] El build es reproducible y no requiere Python en el host.
- [x] El README documenta el aviso de SmartScreen por falta de firma.

## Comments

**2026-11-15 — Implementación.** Rama `ticket/12-13-packaging`, run Native `43777144890` verde. Carpeta `YouTube Downloader/YouTube Downloader.exe` x64 con `console=False`, ícono `.ico` e información de versión (desde `APP_VERSION` en tags), comprimida como `YouTube-Downloader-windows-x64.zip` (17 MB). El smoke (health, Engine `ready`, abrir carpeta, apagado, y el modo sin CA) pasó sobre el `.exe`; la descarga se saltó por el bot check. El job `release` está escrito pero sin ejecutar. Pendiente en un PC real: doble clic sin consola, SmartScreen, descarga de video y playlist, "mostrar archivo", cancelar sin huérfanos y `Idle Shutdown`.

**2026-11-15 — Revisión del orquestador.** Artefacto de macOS del run `43777144890` descargado y extraído con `ditto` en un Mac real (arm64): firma ad-hoc válida (`codesign --verify --deep --strict`), bundle id `io.github.nicosmico.youtube-downloader`, mínimo macOS 13.0, ícono incluido. El smoke contra el ejecutable interno del `.app` completó la descarga real al segundo intento; el primero recibió un `HTTP 403` puntual de YouTube, que la app muestra como "Se interrumpió la conexión con YouTube" con "Reintentar". Pendiente: abrir con doble clic y Gatekeeper en un Mac, Windows en un PC real y la publicación con un tag `v*`.
