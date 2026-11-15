# 07: Opciones nivel 1

**What to build:** La UI permite elegir modo video con `Quality` `2160p`, `1080p`, `720p` o `480p`, o modo audio con `AudioFormat` `mp3`, `m4a` u `opus`. La API y la UI rechazan combinaciones inválidas. La descarga usa el orden de formatos acordado en el spike: a igual resolución prefiere H.264/AAC en `.mp4` (ADR-0009) y mide la `Quality` sobre el lado menor. El audio solo se recodifica cuando el formato pedido no existe de forma nativa. La UI indica junto a `2160p` que puede requerir un reproductor como VLC.

**Blocked by:** 06 (Cola persistente y concurrencia).

**Status:** ready-for-agent

- [ ] Cada `Quality` produce un archivo cuyo lado menor es menor o igual al tope elegido, también en videos verticales.
- [ ] A 1080p o menos, el archivo es H.264/AAC en `.mp4` cuando YouTube lo ofrece.
- [ ] Cada `AudioFormat` produce un archivo reproducible en su formato; `m4a` y `opus` no se recodifican si existe el stream nativo.
- [ ] La API rechaza `quality` en modo audio y `audioFormat` en modo video.
- [ ] La UI impide enviar combinaciones inválidas y muestra el aviso de `2160p`.
- [ ] Tests de contrato de los argumentos de `yt-dlp` por modo y calidad.
- [ ] La selección se conserva al encolar.
