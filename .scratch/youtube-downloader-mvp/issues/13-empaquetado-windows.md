# 13: Empaquetado Windows

**What to build:** Un ejecutable de Windows construido con PyInstaller `onedir` que incluye el build de Angular, con ícono, distribuido en `.zip`. Debe funcionar en Windows 10/11 x64 sin Python, Node ni `ffmpeg` instalados: preparar el Engine y descargar un video.

**Blocked by:** 11 (Historial y multi-pestaña).

**Status:** ready-for-agent

- [ ] El `.exe` arranca en Windows 10/11 x64 sin Python, Node ni `ffmpeg` instalados.
- [ ] Prepara el Engine en el primer arranque y descarga un video.
- [ ] `Single Instance` y el apagado ordenado funcionan desde el bundle.
- [ ] Abrir la carpeta de descargas funciona en Explorer.
- [ ] El build es reproducible con un script.
- [ ] El README documenta el aviso de SmartScreen por falta de firma.
