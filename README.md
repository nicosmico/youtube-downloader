# youtube-downloader

Aplicación de escritorio para descargar videos y audio de YouTube público, con interfaz web local y motor `yt-dlp` autogestionado.

> **Estado:** diseño cerrado, implementación no iniciada. La spec y los tickets están listos.

## Qué hace (MVP)

- Pega una URL de YouTube y obtén un preview con título, miniatura, duración y calidades reales.
- Descarga video en `best`, `2160p`, `1080p`, `720p` o `480p`, priorizando archivos que abra el reproductor del sistema.
- Extrae solo audio en `mp3`, `m4a` u `opus`.
- Playlists y canales (hasta 500 entradas) con entradas seleccionables; una subcarpeta numerada por playlist.
- Cola persistente con máximo dos descargas simultáneas y progreso en vivo.
- Presets, historial, cancelar y reintentar.
- `yt-dlp`, `ffmpeg`, `ffprobe` y Deno se descargan, verifican y actualizan solos: no requiere Python, Node ni `ffmpeg` instalados.
- macOS (Apple Silicon, 13+) y Windows 10/11 x64.

## Cómo funciona

```
Navegador  ──HTTP/SSE──►  FastAPI (127.0.0.1)
                              ├── cola de DownloadJob
                              ├── SQLite
                              └── Engine: yt-dlp + Deno + ffmpeg
```

El ejecutable levanta un servidor local, sirve la SPA de Angular y abre el navegador por defecto. Las descargas corren en el servidor: cerrar la pestaña no las detiene. Si no queda ninguna pestaña abierta ni nada en cola durante 10 minutos, la app se cierra sola. El estado vive en SQLite dentro de `~/.youtube-downloader`.

## Stack

| Capa | Tecnología |
| :--- | :--- |
| Backend | Python 3.13, FastAPI, Uvicorn, SQLite, PyInstaller |
| Frontend | Angular (standalone + signals), servido como estáticos |
| Motor | `yt-dlp` + Deno + `ffmpeg`/`ffprobe` (binarios externos) |
| Transporte | REST + Server-Sent Events |
| Desarrollo | Docker Compose sobre OrbStack, `uv`, `ruff`, `pytest` |
| Empaquetado | GitHub Actions (`macos-latest`, `windows-latest`) y GitHub Releases |

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
.github/workflows tests, builds nativos y releases
docs/              ADRs y documentación de agentes
.scratch/          spec y tickets locales
```

## Desarrollo

Todavía no hay código. El backend y los tests correrán en **Docker Compose** (OrbStack); no hace falta Python en el host. Angular usa Node 24, que ya está instalado, o un contenedor opcional. Ni `ffmpeg` ni Deno se instalan: los gestiona la app.

Dentro del contenedor el servidor escucha en `0.0.0.0` con un puerto fijo (`BIND_HOST`, `PORT`); Compose lo publica solo en `127.0.0.1` del host, monta `~/Downloads` y el directorio de datos, y arranca con `OPEN_BROWSER=0`. El navegador se abre desde el host.

Los comandos de arranque se añadirán con el walking skeleton (ticket 02).

## Empaquetado

Los ejecutables se construyen en **GitHub Actions**: `macos-latest` produce el `.app` arm64 y `windows-latest` el `.exe` x64. Docker no participa en el build nativo porque PyInstaller no cross-compila. Un tag `v*` publica ambos `.zip` en un GitHub Release; los PR generan artefactos de prueba.

## Fuera de alcance del MVP

Sitios distintos de YouTube, directos y mixes, cookies y contenido privado, selector de carpeta, ícono de bandeja, subtítulos, recorte por tiempo, flags extra de `yt-dlp`, SponsorBlock, firma/notarización, Macs Intel, idiomas distintos del español, acceso remoto, Docker como runtime del producto y soporte de Linux para usuarios finales.
