# 04: Preview de video

**What to build:** Al pegar una URL, la app la clasifica (video, playlist, mix, otro sitio) antes de invocar `yt-dlp`. Para un video, la UI muestra automáticamente un `MediaPreview` con título, miniatura, duración, autor y las calidades realmente disponibles, deshabilitando las `Quality` superiores a la máxima. Si la URL de video venía de una lista, ofrece "ver playlist completa". Los errores de sitio no soportado, mix, directo o estreno, contenido no público, video no disponible, URL inválida y timeout se muestran con mensajes claros. El preview no descarga ni crea jobs.

**Blocked by:** 03 (Engine Manager).

**Status:** ready-for-agent

- [ ] Una URL de video público muestra metadatos y calidades coherentes.
- [ ] `watch?v=…&list=…` se trata como video e incluye `playlistUrl`.
- [ ] Una URL que no es de YouTube se rechaza con `unsupported_site` sin invocar `yt-dlp`.
- [ ] Un mix (`list=RD…`) se rechaza con `mix_playlist`; un directo o estreno, con `live_content`.
- [ ] Una URL privada o restringida muestra un mensaje claro de contenido no público.
- [ ] Una URL inválida y un timeout se manejan sin bloquear la API.
- [ ] El preview no crea archivos ni `DownloadJob`.
- [ ] La UI muestra estados de carga y error.
- [ ] Tests unitarios del clasificador de URLs y tests de integración con `FakeEngine`, sin red.
