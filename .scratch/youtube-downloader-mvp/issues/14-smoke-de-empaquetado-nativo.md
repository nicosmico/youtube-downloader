# 14: Smoke de empaquetado nativo

**What to build:** En cuanto existe la primera descarga end-to-end, construir el producto real (no un "hola mundo") con PyInstaller en GitHub Actions para macOS arm64 y Windows x64, y verificar en los runners que el ejecutable prepara el Engine y descarga un video. El objetivo es descubrir pronto los problemas de PyInstaller, rutas, subprocesos y binarios nativos; el pulido de distribución queda para los tickets 12 y 13.

**Blocked by:** 05 (Descarga de un video end-to-end).

**Status:** ready-for-agent

- [ ] El workflow construye el `onedir` en `macos-latest` y `windows-latest` con el build de Angular incluido, y publica artefactos de prueba.
- [ ] En cada runner, el ejecutable arranca con `--no-browser`, responde `/api/health` y llega a Engine `ready`.
- [ ] Un smoke opt-in con red descarga un video corto de YouTube desde el ejecutable en cada runner.
- [ ] "Abrir carpeta" usa `open` en macOS y `explorer` en Windows; se verifica al menos que el comando se invoca sin error.
- [ ] Los problemas encontrados quedan documentados o resueltos antes de seguir con el ticket 06.
