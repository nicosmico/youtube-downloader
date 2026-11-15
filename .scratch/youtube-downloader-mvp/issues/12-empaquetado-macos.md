# 12: Empaquetado macOS

**What to build:** Un workflow de GitHub Actions en `macos-latest` que construye un `.app` con PyInstaller `onedir`, incluye el build de Angular, aplica firma ad-hoc y publica un `.zip` como artefacto. El `.app` debe funcionar en una máquina sin Python, Node ni `ffmpeg` instalados: preparar el Engine y descargar un video. No se compila en el Mac del desarrollador.

**Blocked by:** 11 (Historial y multi-pestaña).

**Status:** ready-for-agent

- [ ] El workflow de `macos-latest` produce el `.app` y lo publica como artefacto.
- [ ] El `.app` descargado arranca en macOS sin Python, Node ni `ffmpeg` instalados.
- [ ] Prepara el Engine en el primer arranque y descarga un video.
- [ ] `Single Instance`, "abrir carpeta" y el apagado ordenado funcionan desde el bundle.
- [ ] El build es reproducible y no requiere Python en el host.
- [ ] El README documenta el aviso de Gatekeeper por falta de notarización.
