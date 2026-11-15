---
status: accepted
---

# A igual resolución, se prefiere el códec que reproduce el sistema

Para una misma resolución YouTube ofrece H.264, VP9 y AV1. VP9 y AV1 suelen pesar menos o verse algo mejor, pero QuickTime y muchos reproductores por defecto no los abren dentro de `.mp4`. Decidimos que la selección de formato ordene primero por la `Quality` pedida y, a igual resolución, prefiera H.264 con audio AAC en contenedor `.mp4`. Solo cuando no hay H.264 a esa resolución (habitualmente 2160p) se acepta VP9 o AV1.

## Considered Options

- **Máxima calidad siempre**: descartada; el usuario recibiría archivos que no abren con doble clic.
- **Solo H.264**: descartada; limitaría `best` y `2160p` a 1080p.
- **Recodificar a H.264**: descartada; lenta, pierde calidad y depende de la CPU del usuario.

## Consequences

- Un archivo `2160p` puede requerir un reproductor como VLC en algunos equipos; la UI lo indica junto a esa opción.
- La selección se expresa con orden de formatos de `yt-dlp` (`-S`) y no con filtros, y sus argumentos quedan cubiertos por tests de contrato.
