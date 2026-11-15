# 12: Empaquetado macOS

**What to build:** Completar el build de macOS iniciado en el ticket 14: `.app` arm64 con PyInstaller `onedir`, build de Angular incluido, firma ad-hoc, ícono, y publicación del `.zip` en un GitHub Release al crear un tag `v*`. El `.app` debe funcionar en macOS 13 o superior sin Python, Node ni `ffmpeg` instalados. No se compila en el Mac del desarrollador.

**Blocked by:** 11 (Historial, multi-pestaña e Idle Shutdown), 14 (Smoke de empaquetado nativo).

**Status:** ready-for-agent

- [ ] Un tag `v*` publica el `.zip` del `.app` en un GitHub Release; los PR producen solo artefactos de prueba.
- [ ] El `.app` descargado arranca en macOS 13+ arm64 sin Python, Node ni `ffmpeg` instalados.
- [ ] Prepara el Engine en el primer arranque y descarga un video y una playlist.
- [ ] `Single Instance`, "abrir carpeta", "mostrar archivo", `Idle Shutdown` y el apagado ordenado funcionan desde el bundle.
- [x] El build es reproducible y no requiere Python en el host.
- [x] El README documenta cómo abrir la app pese a Gatekeeper ("Abrir igualmente" en Privacidad y seguridad) por falta de notarización.

## Comments

**2026-11-15 — Implementación.** Rama `ticket/12-13-packaging`, run Native `43777144890` verde (CI `43777144965` verde). `YouTube Downloader.app` arm64 (Mach-O arm64, bundle id `io.github.nicosmico.youtube-downloader`, `LSMinimumSystemVersion` 13.0, ícono `.icns`), firma ad-hoc verificada con `codesign --verify --deep --strict` antes y después del smoke, y también en el `.zip` descargado y descomprimido con `ditto` (17 MB). El smoke (health, Engine `ready`, abrir carpeta, apagado, y el modo sin CA) pasó sobre el ejecutable interno; la descarga se saltó por el bot check de la IP del runner. El job `release` (`gh release create --generate-notes`, solo con tag `v*`) está escrito pero sin ejecutar. Pendiente en un Mac real: abrir el `.app` con doble clic (Gatekeeper, navegador, sin Terminal), descargar video y playlist, "mostrar archivo" y `Idle Shutdown`.
