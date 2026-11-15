# 05: Descarga de un video end-to-end

**What to build:** Desde el preview, el usuario elige `best` y encola. El `DownloadJob` se persiste sin `Batch`, el runner ejecuta `yt-dlp` en la carpeta de staging del job, la UI muestra progreso, velocidad y ETA por SSE, y al terminar la app mueve el archivo a `DOWNLOAD_DIR` (en desarrollo, el volumen montado; en producción, `~/Downloads`) resolviendo colisiones bajo un lock (ADR-0010). La UI ofrece abrir la carpeta. Cubre los estados `downloading`, `processing`, `completed` y `failed`.

**Blocked by:** 04 (Preview de video).

**Status:** ready-for-agent

- [ ] Un video público se descarga y el archivo aparece en `DOWNLOAD_DIR`; el staging del job queda vacío.
- [ ] `POST /api/jobs` para un video suelto responde `batchId: null`.
- [ ] La UI muestra progreso, velocidad y ETA en vivo.
- [ ] `completed` solo se marca cuando el archivo final está en `DOWNLOAD_DIR`.
- [ ] Dos descargas con el mismo título, incluso simultáneas, generan archivos distintos (` (2)`).
- [ ] El movimiento final funciona entre volúmenes distintos (staging y descargas en montajes separados del contenedor).
- [ ] El endpoint de abrir carpeta responde y la UI muestra el resultado; la apertura nativa en Finder se valida en el ticket 14.
- [ ] Un fallo de `yt-dlp` deja el job `failed` con mensaje saneado y borra su staging.
- [ ] Con el Engine sin `ready`, `POST /api/jobs` responde `engine_not_ready` y la UI no permite encolar.
- [ ] Tests de integración con `FakeEngine` y tests de contrato de argumentos.
