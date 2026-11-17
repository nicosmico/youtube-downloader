---
status: accepted
---

# El MVP expone solo las opciones de nivel 1 y un destino fijo

Exponer las más de 200 flags de `yt-dlp` haría la UI inutilizable. Decidimos que el MVP tenga una sola capa de opciones: URL, `DownloadMode`, `Quality` o `AudioFormat`, y `Preset`. Todo se guarda en `~/Downloads` (con subcarpeta por playlist), sin selector de carpeta. *Sustituido en parte por ADR-0012: la carpeta ya se puede cambiar.*

## Consequences

- Subtítulos, metadatos, recorte por tiempo, flags extra y SponsorBlock quedan pospuestos, no descartados.
- No se ofrece elegir carpeta; existe un botón para abrir `~/Downloads` en Finder/Explorer.
- Los `Preset` cubren la repetición sin multiplicar controles.
