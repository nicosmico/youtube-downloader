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
- [ ] El build es reproducible y no requiere Python en el host.
- [ ] El README documenta el aviso de SmartScreen por falta de firma.
