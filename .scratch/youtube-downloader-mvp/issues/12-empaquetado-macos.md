# 12: Empaquetado macOS

**What to build:** Completar el build de macOS iniciado en el ticket 14: `.app` arm64 con PyInstaller `onedir`, build de Angular incluido, firma ad-hoc, ícono, y publicación del `.zip` en un GitHub Release al crear un tag `v*`. El `.app` debe funcionar en macOS 13 o superior sin Python, Node ni `ffmpeg` instalados. No se compila en el Mac del desarrollador.

**Blocked by:** 11 (Historial, multi-pestaña e Idle Shutdown), 14 (Smoke de empaquetado nativo).

**Status:** ready-for-agent

- [ ] Un tag `v*` publica el `.zip` del `.app` en un GitHub Release; los PR producen solo artefactos de prueba.
- [ ] El `.app` descargado arranca en macOS 13+ arm64 sin Python, Node ni `ffmpeg` instalados.
- [ ] Prepara el Engine en el primer arranque y descarga un video y una playlist.
- [ ] `Single Instance`, "abrir carpeta", "mostrar archivo", `Idle Shutdown` y el apagado ordenado funcionan desde el bundle.
- [ ] El build es reproducible y no requiere Python en el host.
- [ ] El README documenta cómo abrir la app pese a Gatekeeper ("Abrir igualmente" en Privacidad y seguridad) por falta de notarización.
