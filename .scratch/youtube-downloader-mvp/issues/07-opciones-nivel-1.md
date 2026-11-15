# 07: Opciones nivel 1

**What to build:** La UI permite elegir modo video con `Quality` `2160p`, `1080p`, `720p` o `480p`, o modo audio con `AudioFormat` `mp3`, `m4a` u `opus`. La API y la UI rechazan combinaciones inválidas. La descarga usa los argumentos correctos de `yt-dlp` y el audio se convierte con `ffmpeg`.

**Blocked by:** 06 (Cola persistente y concurrencia).

**Status:** ready-for-agent

- [ ] Cada `Quality` produce un archivo con altura menor o igual al tope elegido.
- [ ] Cada `AudioFormat` produce un archivo reproducible en su formato.
- [ ] La API rechaza `quality` en modo audio y `audioFormat` en modo video.
- [ ] La UI impide enviar combinaciones inválidas.
- [ ] Tests de contrato de los argumentos de `yt-dlp` por modo y calidad.
- [ ] La selección se conserva al encolar.
