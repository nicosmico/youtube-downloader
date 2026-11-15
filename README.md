# youtube-downloader

Aplicación de escritorio para descargar videos y audio de YouTube público, con interfaz web local y motor `yt-dlp` autogestionado.

> **Estado:** diseño cerrado, implementación no iniciada. La spec y los tickets están listos.

## Qué hace (MVP)

- Pega una URL y obtén un preview con título, miniatura, duración y calidades reales.
- Descarga video en `best`, `2160p`, `1080p`, `720p` o `480p`.
- Extrae solo audio en `mp3`, `m4a` u `opus`.
- Playlists con entradas seleccionables; una subcarpeta por playlist.
- Cola persistente con máximo dos descargas simultáneas y progreso en vivo.
- Presets, historial, cancelar y reintentar.
- `yt-dlp`, `ffmpeg` y `ffprobe` se descargan y actualizan solos: no requiere Python, Node ni `ffmpeg` instalados.
- macOS y Windows.

## Cómo funciona

```
Navegador  ──HTTP/SSE──►  FastAPI (127.0.0.1)
                              ├── cola de DownloadJob
                              ├── SQLite
                              └── yt-dlp + ffmpeg
```

El ejecutable levanta un servidor local, sirve la SPA de Angular y abre el navegador por defecto. Las descargas corren en el servidor: cerrar la pestaña no las detiene. El estado vive en SQLite dentro de `~/.youtube-downloader`.

## Stack

| Capa | Tecnología |
| :--- | :--- |
| Backend | Python, FastAPI, Uvicorn, SQLite, PyInstaller |
| Frontend | Angular, servido como estáticos |
| Motor | `yt-dlp` + `ffmpeg`/`ffprobe` (binarios externos) |
| Transporte | REST + Server-Sent Events |
| Desarrollo | Docker Compose sobre OrbStack |
| Empaquetado | GitHub Actions (`macos-latest`, `windows-latest`) |

## Documentación

- [Glosario del dominio](GLOSSARY.md)
- [Decisiones de arquitectura (ADRs)](docs/adr/)
- [Spec del MVP](.scratch/youtube-downloader-mvp/spec.md)
- [Tickets de implementación](.scratch/youtube-downloader-mvp/issues/)
- [Instrucciones para agentes](AGENTS.md)

## Estructura planeada

```
backend/          FastAPI, runner, Engine Manager, SQLite
frontend/         workspace Angular
packaging/        PyInstaller y scripts de build
compose.yaml      entorno de desarrollo
.github/workflows tests y builds nativos
docs/              ADRs y documentación de agentes
.scratch/          spec y tickets locales
```

## Desarrollo

Todavía no hay código. El backend y los tests correrán en **Docker Compose** (OrbStack); no hace falta Python en el host. Angular usa Node 24, que ya está instalado, o un contenedor opcional. `ffmpeg` no se instala: lo gestiona la app.

El contenedor publica el puerto en `127.0.0.1`, monta `~/Downloads` y el directorio de datos, y arranca con `OPEN_BROWSER=0`; el navegador se abre desde el host.

Los comandos de arranque se añadirán con el walking skeleton (ticket 02).

## Empaquetado

Los ejecutables se construyen en **GitHub Actions**: `macos-latest` produce el `.app` y `windows-latest` el `.exe`. Docker no participa en el build nativo porque PyInstaller no cross-compila. Cada runner publica el artefacto listo para probar en una máquina limpia.

## Fuera de alcance del MVP

Cookies y contenido privado, selector de carpeta, ícono de bandeja, subtítulos, recorte por tiempo, flags extra de `yt-dlp`, SponsorBlock, firma/notarización, acceso remoto, Docker como runtime del producto y soporte de Linux para usuarios finales.
