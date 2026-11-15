# 04: Preview de video

**What to build:** Al pegar una URL de video, la UI muestra automáticamente un `MediaPreview` con título, miniatura, duración, autor y las calidades realmente disponibles. Los errores de contenido no público, video no disponible, URL inválida y timeout se muestran con mensajes claros. El preview no descarga ni crea jobs.

**Blocked by:** 03 (Engine Manager).

**Status:** ready-for-agent

- [ ] Una URL de video público muestra metadatos y calidades coherentes.
- [ ] Una URL privada o restringida muestra un mensaje claro de contenido no público.
- [ ] Una URL inválida y un timeout se manejan sin bloquear la API.
- [ ] El preview no crea archivos ni `DownloadJob`.
- [ ] La UI muestra estados de carga y error.
- [ ] Tests de integración con `FakeEngine`, sin red.
