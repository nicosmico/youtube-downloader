# 12: Empaquetado macOS

**What to build:** Un `.app` de macOS construido con PyInstaller `onedir` que incluye el build de Angular, con ícono y firma ad-hoc, distribuido en `.zip`. Debe funcionar en una máquina sin Python, Node ni `ffmpeg` instalados: preparar el Engine y descargar un video.

**Blocked by:** 11 (Historial y multi-pestaña).

**Status:** ready-for-agent

- [ ] El `.app` arranca en macOS sin Python, Node ni `ffmpeg` instalados.
- [ ] Prepara el Engine en el primer arranque y descarga un video.
- [ ] `Single Instance` y el apagado ordenado funcionan desde el bundle.
- [ ] El build es reproducible con un script.
- [ ] El README documenta el aviso de Gatekeeper por falta de notarización.
