---
status: accepted
---

# Solo contenido público de YouTube, sin cookies ni cuentas

El soporte de autenticación y de `--cookies-from-browser` es frágil entre macOS y Windows, y el producto no lo necesita. Decidimos que la app solo descargue `Contenido público` de YouTube y que falle con un mensaje claro cuando YouTube exija inicio de sesión o verificación.

Aunque `yt-dlp` soporta cientos de sitios, la app solo acepta URLs de `youtube.com`, `youtu.be` y `music.youtube.com`: cada sitio extra trae sus propios modos de fallo y la UI promete calidades y mensajes pensados para YouTube.

## Consequences

- Videos privados, con restricción de edad o con muro de login quedan fuera de alcance.
- Se rechazan directos y estrenos pendientes, porque la descarga no tendría fin, y mixes automáticos (`list=RD…`), porque son listas casi infinitas.
- Los canales se tratan como `Playlist`; el `MediaPreview` lista como máximo 500 `Entry`.
- Una URL `watch?v=…&list=…` se trata como video; la UI ofrece abrir la playlist completa.
- No hay superficie de riesgo asociada a credenciales del usuario.
