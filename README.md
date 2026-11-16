# youtube-downloader

Aplicación de escritorio para descargar videos y audio de YouTube público, con interfaz web local y motor `yt-dlp` autogestionado.

> **Estado:** MVP en construcción. Funcionan el Engine autogestionado, el preview, las descargas de video y audio, la cola persistente, los atajos de calidad y las playlists; faltan cancelar y reintentar, el historial y los paquetes finales de macOS y Windows.

## Qué hace (MVP)

- Pega una URL de YouTube y obtén un preview con título, miniatura, duración y calidades reales.
- Descarga video en `best`, `2160p`, `1080p`, `720p` o `480p`, priorizando archivos que abra el reproductor del sistema.
- Extrae solo audio en `mp3`, `m4a` u `opus`.
- Playlists y canales (hasta 500 entradas) con entradas seleccionables; una subcarpeta numerada por playlist.
- Cola persistente con máximo dos descargas simultáneas y progreso en vivo.
- Dos atajos de un clic ("Mejor video" y "MP3"), historial, cancelar y reintentar.
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

El backend y los tests corren en **Docker Compose** (OrbStack); no hace falta Python en el host. Angular usa Node 24 local. Ni `ffmpeg` ni Deno se instalan: los gestiona la app.

Dentro del contenedor el servidor escucha en `0.0.0.0` con un puerto fijo (`BIND_HOST`, `PORT`, solo desarrollo; sin ellos el `Launcher` hace bind a `127.0.0.1:0`). Compose lo publica solo en `127.0.0.1` del host, monta `~/Downloads` y `./.dev-data` (nunca el `~/.youtube-downloader` real, que se llenaría de binarios Linux) y arranca con `OPEN_BROWSER=0`. El navegador se abre desde el host.

### Arrancar la app

```sh
docker compose up --build        # imagen multi-stage: compila Angular y lo sirve FastAPI
open http://127.0.0.1:8765/      # macOS; el puerto se cambia con PORT=9000 docker compose up
curl http://127.0.0.1:8765/api/health
docker compose down              # o el botón "Cerrar aplicación" de la UI
```

Variables útiles: `PORT`, `HOST_DATA_DIR` y `HOST_DOWNLOAD_DIR` (carpetas del host que se montan en `/data` y `/downloads`).

En el primer arranque con `./.dev-data/bin` vacío, la app descarga el Engine Linux (~240 MB) en segundo plano: `curl http://127.0.0.1:8765/api/system/engine` pasa de `installing` a `ready` y `./.dev-data/engine.json` guarda versión y SHA-256 de cada binario. Si falla (sin red, hash incorrecto), el estado es `error`; se reintenta con el botón "Reintentar" o con `POST /api/system/engine/install`. `ENGINE_BIN_DIR=<carpeta>` (carpeta montada en el contenedor) usa esos binarios tal cual, sin descargar ni fijar hashes: solo comprueba `--version`.

Single Instance en Compose: el lock vive en el directorio de datos montado, así que un segundo contenedor con el mismo `HOST_DATA_DIR` falla con "Another instance is starting or stuck" (cada contenedor tiene su propia red y no puede alcanzar el puerto del otro). Fuera de Docker, el segundo `Launcher` abre el navegador en la instancia existente y termina.

### Tests y lint (backend)

```sh
docker compose run --rm tests                      # pytest (sin red)
docker compose run --rm tests pytest -m network    # opt-in: instala el Engine real en un directorio temporal
docker compose run --rm tests ruff check .         # lint
docker compose run --rm tests ruff format --check . # formato (sin --check aplica el formato)
docker compose run --rm tests uv lock              # regenerar uv.lock tras cambiar dependencias
```

CI ejecuta exactamente estos comandos. `./backend` se monta en el contenedor `tests`, así que los cambios se ven sin reconstruir; reconstruye (`docker compose build tests`) solo si cambian las dependencias.

### Frontend

```sh
cd frontend
npm ci
npm start             # ng serve en :4200, con proxy de /api a 127.0.0.1:8765 (requiere docker compose up)
npm run test:ci       # Vitest + jsdom, sin navegador
npm run build         # escribe en backend/app/static (ignorado por git)
```

`npm run build` deja la SPA lista para el `Launcher` fuera de Docker; la imagen de Compose siempre compila su propia copia.

## Descargar e instalar

Descarga el `.zip` de tu sistema desde la última versión en [GitHub Releases](../../releases/latest). No hace falta instalar Python, Node ni `ffmpeg`. La app no está firmada ni notarizada, por eso el sistema muestra un aviso la primera vez.

**macOS 13 o superior (Apple Silicon)**: `YouTube-Downloader-macos-arm64.zip`

1. Descomprime y mueve `YouTube Downloader.app` a Aplicaciones.
2. Al abrirla, macOS la bloquea. En macOS 15 o superior ve a Ajustes del Sistema › Privacidad y seguridad y pulsa "Abrir igualmente". En versiones anteriores, clic derecho sobre la app › Abrir.
3. La app abre el navegador con su interfaz. Sigue funcionando en segundo plano hasta que pulses "Cerrar aplicación" o pasen 10 minutos sin uso.

**Windows 10/11 (x64)**: `YouTube-Downloader-windows-x64.zip`

1. Descomprime la carpeta completa y ejecuta `YouTube Downloader.exe`.
2. Si SmartScreen avisa, pulsa "Más información" › "Ejecutar de todos modos".
3. Se abre el navegador; se cierra igual que en macOS.

En el primer arranque la app descarga el Engine (`yt-dlp`, `ffmpeg` y Deno, unos 250 MB), así que necesita conexión a internet.

## Empaquetado

Los ejecutables se construyen en **GitHub Actions**: `macos-latest` produce el `.app` arm64 (firma ad-hoc) y `windows-latest` la carpeta con el `.exe` x64; ambos se comprimen en `.zip`. Docker no participa en el build nativo porque PyInstaller no cross-compila. Un tag `v*` publica ambos `.zip` en un GitHub Release; los PR generan artefactos de prueba.

## Fuera de alcance del MVP

Sitios distintos de YouTube, directos y mixes, cookies y contenido privado, selector de carpeta, ícono de bandeja, subtítulos, recorte por tiempo, flags extra de `yt-dlp`, SponsorBlock, firma/notarización, Macs Intel, idiomas distintos del español, acceso remoto, Docker como runtime del producto y soporte de Linux para usuarios finales.
