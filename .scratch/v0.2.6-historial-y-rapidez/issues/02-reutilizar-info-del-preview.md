# 02: La descarga reutiliza la información del preview

**What to build:** Medido en un Mac: una descarga de audio de 2 min tarda 3,5 s, de los que 2,6 s son `yt-dlp` volviendo a extraer la información del vídeo. Con `--load-info-json` sobre el JSON que ya produjo el preview (`-J`), tarda 0,9 s; `yt-dlp` vuelve a elegir el formato con los `-f`/`-S` de la descarga a partir de la lista de formatos del JSON. Backend solo.

**Blocked by:** None.

**Status:** ready-for-agent

## Diseño

- **Caché en memoria del preview de vídeos sueltos** (`backend/app/preview/service.py` o un módulo pequeño junto a él): guarda la salida JSON en bruto de `-J` (tal cual la devolvió `yt-dlp`) indexada por la URL canónica (`classified.url`), con la hora en que se obtuvo (reloj inyectable). Límite: 20 entradas (LRU) y validez de **1 hora** (las URLs de formato de YouTube caducan en unas 6 h). Las playlists no se guardan. Debe ser segura entre hilos (el preview corre en el threadpool de FastAPI y el runner en sus hilos).
- **Al ejecutar un job de un vídeo suelto** (`backend/app/jobs/runner.py` y `arguments.py`): si la caché tiene una entrada válida para `job.url` **en el momento de arrancar** (no al encolar), escribir el JSON en la carpeta de staging del job (p. ej. `info.json`) y usar `--load-info-json <ruta>` en lugar de la URL al final de los argumentos. El resto de argumentos no cambia. Cuidado: `find_staged_file` no debe confundir ese `info.json` con el archivo descargado (ponlo fuera del patrón que busca, o bórralo antes de buscar).
- **Respaldo transparente:** si `yt-dlp` sale con error usando la información reutilizada (y el job no fue cancelado ni interrumpido), se repite una vez de inmediato **sin** ella (con la URL), dentro del mismo Attempt: el usuario no ve un fallo ni un intento extra. Registrar en el log `"job %s: cached info failed, retrying from the URL"`. La entrada de la caché se descarta.
- Los jobs de playlist (con `batch_id`) no usan la caché.
- Inyección: el runner recibe la caché (o una función `lookup(url) -> str | None`) desde `main.py`, como las demás dependencias.
- Sin cambios en la API ni en el frontend.

## Acceptance criteria

- [ ] Caché con TTL de 1 h, límite LRU de 20, solo vídeos sueltos, segura entre hilos. Tests con reloj falso.
- [ ] Un job de vídeo suelto con preview reciente arranca con `--load-info-json` y sin URL; sin preview o con uno caducado, con la URL como hoy. Tests.
- [ ] Si falla con la información reutilizada, se repite con la URL de forma transparente (un único Attempt, sin estado `failed` intermedio publicado). Test con el motor falso.
- [ ] Cancelar durante la ejecución con información reutilizada no dispara el respaldo. Test.
- [ ] `info.json` nunca se mueve a la carpeta de descargas. Test.
- [ ] `docker compose run --rm tests`, `ruff check .`, `ruff format --check .`.

## Comments
