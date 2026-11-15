# 05: Descarga de un video end-to-end

**What to build:** Desde el preview, el usuario elige `best` y encola. El `DownloadJob` se persiste, el runner ejecuta `yt-dlp`, la UI muestra progreso, velocidad y ETA por SSE, y al terminar el archivo aparece en `~/Downloads`. La colisión de nombres se resuelve sin sobrescribir y la UI ofrece abrir la carpeta. Cubre los estados `downloading`, `processing`, `completed` y `failed`.

**Blocked by:** 04 (Preview de video).

**Status:** ready-for-agent

- [ ] Un video público se descarga y el archivo aparece en `~/Downloads`.
- [ ] La UI muestra progreso, velocidad y ETA en vivo.
- [ ] `completed` solo se marca cuando el archivo final existe.
- [ ] Dos descargas con el mismo título generan archivos distintos.
- [ ] Abrir la carpeta de descargas funciona en macOS.
- [ ] Un fallo de `yt-dlp` deja el job `failed` con mensaje saneado.
- [ ] Tests de integración con `FakeEngine` y tests de contrato de argumentos.
