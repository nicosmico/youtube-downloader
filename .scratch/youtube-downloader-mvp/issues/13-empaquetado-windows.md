# 13: Empaquetado Windows

**What to build:** Un workflow de GitHub Actions en `windows-latest` que construye un `onedir` con PyInstaller, incluye el build de Angular, aplica ícono y publica un `.zip` como artefacto. El `.exe` debe funcionar en Windows 10/11 x64 sin Python, Node ni `ffmpeg` instalados: preparar el Engine y descargar un video. No se compila en el Mac del desarrollador.

**Blocked by:** 11 (Historial y multi-pestaña).

**Status:** ready-for-agent

- [ ] El workflow de `windows-latest` produce el `.exe` y lo publica como artefacto.
- [ ] El `.exe` descargado arranca en Windows 10/11 x64 sin Python, Node ni `ffmpeg` instalados.
- [ ] Prepara el Engine en el primer arranque y descarga un video.
- [ ] `Single Instance`, "abrir carpeta" en Explorer y el apagado ordenado funcionan desde el bundle.
- [ ] El build es reproducible y no requiere Python en el host.
- [ ] El README documenta el aviso de SmartScreen por falta de firma.
