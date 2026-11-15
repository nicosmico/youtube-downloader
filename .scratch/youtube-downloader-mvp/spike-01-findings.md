# Spike 01: hallazgos (Engine, Docker y empaquetado)

Fecha: 2026-11-15. Rama `spike/01`. Código desechable en `spike/`. Hosts de prueba: macOS arm64 (binarios reales ejecutados), contenedor Linux arm64 (OrbStack) y Linux x86_64 (emulado en OrbStack). Windows: solo URLs y fuentes de hash.

Versiones validadas: `yt-dlp` 2026.10.26, Deno v2.9.8, FFmpeg 9.0.2.

## Estado del checklist del ticket

| Ítem | Estado | Nota |
| :--- | :--- | :--- |
| Descarga, SHA-256 y versión en contenedor Linux | OK | arm64 y x86_64. Script de referencia: ver "Fuentes por plataforma". |
| Assets y fuente de hashes macOS arm64 / Windows x64 | OK | macOS ejecutado en el host. Windows solo URL + hash (HEAD/API). |
| Proveedor de `ffmpeg` por plataforma | OK | Decisión abierta en Windows (ver abajo). |
| Flag de `yt-dlp` para la ruta de Deno | OK | `--js-runtimes deno:<ruta>`. |
| `--progress` + `--print after_move:filepath` | OK | Con matices (ver "Progreso"). |
| Fórmula `-S` por `Quality` | OK | Verificada con 3 videos (4K, Short vertical, 240p). |
| `--merge-output-format mp4` sin recodificar; `m4a`/`opus` sin recodificar | OK | `-c copy` en los tres casos. |
| `yt-dlp -U` en Windows con otro `yt-dlp.exe` en uso | PARCIAL | Análisis del código fuente + job de Actions preparado, sin ejecutar. |
| FastAPI hola mundo en Docker Compose | OK | Alcanzable en 127.0.0.1, rechazado en la IP LAN. |
| PyInstaller `onedir` en `macos-latest` | PENDIENTE (GitHub) | Workflow preparado, no ejecutado. |
| PyInstaller sin consola en `windows-latest` | PENDIENTE (GitHub) | Idem. |
| Hallazgos en spec/ADR | PENDIENTE | Ver "Cambios propuestos". El orquestador los aplica. |

El build local de PyInstaller en macOS se omitió: `uv` no está en el host y no se instala nada. Como sustituto se construyó el `onedir` dentro de un contenedor Linux (Python 3.13 + uv): arranca con `--no-browser --port`, sirve `/api/health` y el `index.html` empaquetado (el `--add-data` y `sys._MEIPASS` funcionan; 33 MB). En `python:3.13-slim` PyInstaller exige `binutils` (no aplica a los runners de Actions).

## Fuentes por plataforma

| Binario | linux arm64 (dev) | linux x64 (CI) | macOS arm64 | Windows x64 |
| :--- | :--- | :--- | :--- | :--- |
| yt-dlp | `yt-dlp_linux_aarch64` | `yt-dlp_linux` | `yt-dlp_macos` (universal2, firma ad-hoc) | `yt-dlp.exe` |
| Deno | `deno-aarch64-unknown-linux-gnu.zip` | `deno-x86_64-unknown-linux-gnu.zip` | `deno-aarch64-apple-darwin.zip` | `deno-x86_64-pc-windows-msvc.zip` |
| ffmpeg + ffprobe | martin-riedl release 9.0.2 `linux/arm64/1789931697_9.0.2/{ffmpeg,ffprobe}.zip` | `linux/amd64/1789931100_9.0.2/...` | `macos/arm64/1789931890_9.0.2/{ffmpeg,ffprobe}.zip` (28 MB c/u) | ver "ffmpeg en Windows" |

URLs base:

- yt-dlp: `https://github.com/yt-dlp/yt-dlp/releases/download/2026.10.26/<asset>`.
- Deno: `https://github.com/denoland/deno/releases/download/v2.9.8/<asset>`.
- martin-riedl: `https://ffmpeg.martin-riedl.de/download/<os>/<arch>/<build>/<ffmpeg|ffprobe>.zip`.

Origen de los hashes:

- **yt-dlp**: `SHA2-256SUMS` del mismo release (formato `hash  asset`). Coincidió en macOS y Linux x64/arm64. `yt-dlp.exe` aparece en el mismo archivo (`f5389d36...7a7d`). Además, la API de GitHub expone `digest` por asset.
- **Deno**: `<asset>.sha256sum` (zip) en el release. En Linux y macOS el formato es `hash  archivo`. **En Windows el archivo está en formato `Get-FileHash` de PowerShell** (líneas `Algorithm/Hash/Path`, hash en MAYÚSCULAS): hay que parsearlo distinto o, mejor, fijar el hash en el código. El `digest` de la API de GitHub coincide (`cba84b26...93bf`).
- **ffmpeg martin-riedl**: archivo `<zip>.sha256` junto a cada descarga. Coincidió. Cada zip contiene un único ejecutable (`ffmpeg` o `ffprobe`), por lo que hay dos descargas.
- **ffmpeg Windows**: ver abajo.

Los hashes de ffmpeg/ffprobe/Deno quedan fijados en el código de la app (ADR-0002). Hashes verificados en este spike:

- Deno macOS arm64: `9f0bf660393da2eaff044cdc7444cb08c73f235849b61d224d825a194ce7c98e`.
- Deno Windows x64: `cba84b26e0df5ae7f74fc66b86a95b866872a86292ebd84fa1e959927edd93bf`.
- ffmpeg macOS arm64: `c8ed4c4e6978a03c485edbfe4e0a5dc2380f8a30bba5150531b31b094492d924`.
- ffprobe macOS arm64: `fcbe839537485eaee7a7a8bc5cbc0f90d53617e80943e8a5b2e31cb851197ea6`.
- yt-dlp macOS: `0f922c15ccc0b83eefa1c8bc9104e434318c4bf16e408e1ee93b7745a6efe0aa`.

Comprobaciones en macOS arm64: los cuatro binarios ejecutan sin Gatekeeper (descargados con `curl` no llevan cuarentena; `ffmpeg`/`ffprobe`/`deno` vienen firmados con hardened runtime, `yt-dlp_macos` ad-hoc). `ffmpeg` solo enlaza frameworks del sistema (estático). Tamaños: deno 78 MB, ffmpeg 63 MB, ffprobe 63 MB, yt-dlp 36 MB.

### ffmpeg en Windows (decisión abierta)

Martin Riedl no ofrece Windows. Opciones verificadas:

| Opción | Asset | Tamaño | Hash | Estabilidad del pin |
| :--- | :--- | :--- | :--- | :--- |
| BtbN (spec actual) | `ffmpeg-n9.0.2-57-gd838f9f9ae-win64-gpl-9.0.zip` en tag `autobuild-2026-11-15-12-40` | 195 MB | `checksums.sha256` del release | Frágil: BtbN solo mantiene una cantidad limitada de releases (38 al consultar: autobuilds recientes más algunos antiguos); los demás se borran. Un hash fijado puede dejar de ser descargable. |
| Gyan (recomendada) | `https://github.com/GyanD/codexffmpeg/releases/download/9.0.2/ffmpeg-9.0.2-essentials_build.zip` | 109 MB | `https://www.gyan.dev/ffmpeg/builds/packages/ffmpeg-9.0.2-essentials_build.zip.sha256` (coincide con el `digest` de la API: `60f46726...47ba`) | Estable: tags de versión permanentes, misma versión 9.0.2 que macOS/Linux. Es el enlace que enlaza ffmpeg.org. |

Ambas traen `bin/ffmpeg.exe` y `bin/ffprobe.exe` dentro de un zip con carpeta raíz versionada: hay que extraer solo esos dos. La spec propone BtbN para Windows y Linux; recomiendo **martin-riedl (release) para macOS arm64 y Linux, y Gyan essentials 9.0.2 para Windows**. Si se prefiere BtbN, hay que reflejar el asset en un release propio para que el hash fijado no caduque.

## Flag de Deno y comportamiento sin Deno

- Flag: `--js-runtimes RUNTIME[:PATH]` (el `PATH` puede ser el binario o su directorio). Confirmado con `yt-dlp --help` y en ejecución: `--js-runtimes deno:/ruta/deno`. Log: `[youtube] [jsc:deno] Solving JS challenges using deno`.
- `--no-js-runtimes` limpia los runtimes (incluido el `deno` por defecto buscado en `PATH`). Sin flag, `yt-dlp` solo busca `deno` en el `PATH`; el Engine debe pasar siempre la ruta explícita.
- Los binarios oficiales ya incluyen `yt-dlp-ejs`; no hace falta `--remote-components`.
- Sin Deno (`--no-js-runtimes`): aparece `WARNING: [youtube] No supported JavaScript runtime could be found... some formats may be missing`. En esta versión el listado `-F` salió casi completo en dos videos (incluido 2160p); solo faltó el formato muxed `18` en "Me at the zoo" y se omitió el cliente `tv samsung`. No se probó si las URLs sin resolver el desafío fallan o se estrangulan al descargar. Conclusión: Deno sigue siendo obligatorio por la advertencia de deprecación, pero la degradación es silenciosa y variable; el preflight del Engine debe exigir `deno --version` OK antes de marcar `ready`.
- **Trampa importante**: sin `--ffmpeg-location` válido, `yt-dlp` usa como formato por defecto `b` (muxed, p. ej. 640x360 itag 18) en vez de `bv*+ba/b`. Cualquier invocación (incluido el preview de calidades y los `--print` de simulación) debe pasar `--ffmpeg-location`.

## Progreso (`--progress`, `--print`)

Comando probado:

```
yt-dlp --ffmpeg-location <bin> --js-runtimes deno:<bin>/deno --no-playlist --newline --progress --no-overwrites \
  --progress-template "download:PROGRESS%(progress)j" \
  --progress-template "postprocess:POSTPROC%(progress)j" \
  --print after_move:filepath -P <staging> -o "%(title)s.%(ext)s" \
  -S "res:480,vcodec:h264,acodec:aac" --merge-output-format mp4 <url>
```

- `--print` implica `--quiet` y `--simulate`, salvo que se use un `WHEN` posterior (`after_move`): con `after_move:filepath` sí descarga. Confirmado en `--help`.
- Con `--progress` + `--newline` se mantienen las líneas de descarga en **stdout**, una por actualización, con el JSON completo de `%(progress)j`. Última línea de stdout: la ruta final de `after_move:filepath`.
- Las líneas `postprocess:` salen por **stderr** en modo quiet, no por stdout: el runner debe leer ambos streams.
- Ejemplo de línea de descarga (campos útiles; también trae `tmpfilename`, `filename` y claves `_..._str`):

```
PROGRESS{"status": "downloading", "downloaded_bytes": 15360, "total_bytes": 404253, "eta": 0, "speed": 1686064.1, "elapsed": 0.479, "_percent": 3.79, ...}
PROGRESS{"downloaded_bytes": 404253, "total_bytes": 404253, "status": "finished", "elapsed": 0.76, ...}
```

- Ejemplo de postproceso (stderr). Para video: `Merger`, luego `MoveFiles`. Para audio: `FixupM4a` (solo m4a), `ExtractAudio`, `MoveFiles`:

```
POSTPROC{"status": "started", "postprocessor": "Merger", "_default_template": "Merger started"}
POSTPROC{"status": "finished", "postprocessor": "Merger", ...}
POSTPROC{"status": "started", "postprocessor": "MoveFiles", ...}
```

- Matices para el parser:
  1. Con video+audio separados hay **dos descargas consecutivas** (video y luego audio): el porcentaje llega a 100 dos veces y cada stream emite un `"status": "finished"` que NO es el fin del job. Para un porcentaje monótono, sumar `downloaded_bytes` de los streams terminados al del stream actual (distinguir por `filename`) o aceptar que el avance reinicia.
  2. `total_bytes` puede faltar y venir `total_bytes_estimate` (m3u8, fragmentos): el parser debe tolerar `null`.
  3. Regla propuesta para `processing`: pasar a `processing` al primer `POSTPROC` con `status: started` cuyo `postprocessor` no sea `MoveFiles` (o al terminar el último stream). `completed` solo tras mover desde staging (ADR-0010), no al ver `MoveFiles finished`, porque ese `MoveFiles` es de `yt-dlp` dentro del staging.

## Fórmula `-S` por `Quality` (ADR-0009)

Plantilla: `-S "res:<N>,vcodec:h264,acodec:aac" --merge-output-format mp4`. Para `best`: `-S "res,vcodec:h264,acodec:aac"` (sin tope). No se usa `-f`: el default `bv*+ba/b` aplica (requiere `--ffmpeg-location`).

- `res` en `-S` se mide sobre el lado menor (`min(width, height)`), por lo que un Short 1080x1920 cuenta como 1080.
- Un valor `res:N` significa "el mayor `res` ≤ N; si no hay ninguno, el menor por encima".

| Quality | `-S` |
| :--- | :--- |
| best | `res,vcodec:h264,acodec:aac` |
| 2160p | `res:2160,vcodec:h264,acodec:aac` |
| 1080p | `res:1080,vcodec:h264,acodec:aac` |
| 720p | `res:720,vcodec:h264,acodec:aac` |
| 480p | `res:480,vcodec:h264,acodec:aac` |

Resultado con `--print` (itag, vcodec, acodec, tamaño):

| Video | best / 2160p | 1440 (no es Quality) | 1080p | 720p | 480p |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 4K horizontal (`2PuFyjAs7JA`) | 313+140 vp9 3840x2160 | 271+140 vp9 2560x1440 | 137+140 avc1 1920x1080 | 136+140 avc1 1280x720 | 135+140 avc1 854x480 |
| Short vertical (`Jt5fgKBqZSY`, 1080x1920) | 137+140 avc1 1080x1920 | igual | 137+140 avc1 1080x1920 | 136+140 avc1 720x1280 | 135+140 avc1 480x854 |

- A 1080p o menos elige H.264 + AAC (itag 140 `mp4a.40.2`). En 2160p y 1440p, donde no hay H.264, cae a VP9 (webm, itag 313/271) antes que AV1 (401/400) y que las variantes m3u8 (625/620). El audio sigue siendo AAC.
- El Short vertical con 1080p no se reduce a 608x1080: se conserva 1080x1920. 720p y 480p dan 720x1280 y 480x854, es decir, el lado menor respeta el tope.
- Si el video no llega al tope pedido, toma su máximo (p. ej. un video de 240p con `2160p` baja el 240p): la UI ya deshabilita calidades por encima del máximo.
- Los formatos H.264 por HLS (itag 270, 1961 kbps) no ganaron a los HTTPS (137) a pesar de su mayor bitrate.

### Contenedor y recodificación

- `--merge-output-format mp4` con VP9 + AAC (caso 2160p): el log `-v` muestra `ffmpeg ... -i video.webm -i audio.m4a -c copy -map 0:v:0 -map 1:a:0 ...`; `ffprobe` del resultado: `vp9 3840x2160` + `aac`. Mux sin recodificar (16 MB, 11 s). Sin la flag, `yt-dlp` mezclaría en `mkv` para VP9+AAC. Un `.mp4` con VP9 puede no abrir en QuickTime (de ahí el aviso de ADR-0009 para 2160p).
- Con H.264 + AAC el `-c copy` es el mismo comando (probado en 480p: `.mp4` de 589 KB).

### Audio

Siempre `-x --audio-quality 0 --audio-format <fmt>` con un `-f` que escoja el stream nativo:

| AudioFormat | `-f` | Resultado verificado |
| :--- | :--- | :--- |
| m4a | `ba[acodec^=mp4a]/ba` | Baja `.m4a` (itag 140, AAC). `FixupM4a` hace `-c copy`. `ExtractAudio`: "Not converting audio ...; file is already in target format m4a". Sin recodificar. |
| opus | `ba[acodec=opus]/ba` | Baja `.webm` (opus); `ExtractAudio` ejecuta `ffmpeg -vn -acodec copy ... .opus`. Sin recodificar; `ffprobe`: `opus`. |
| mp3 | `ba` | `ffmpeg -vn -acodec libmp3lame -q:a 0.0 ... .mp3`. Siempre recodifica. `--audio-quality 0` solo afecta a este caso. |

Si el video no ofrece el códec nativo, el `/ba` de respaldo cae a recodificación (esperable y aceptable).

## `yt-dlp -U` en Windows con otra instancia en uso

No se pudo ejecutar (sin Windows). Análisis de `yt_dlp/update.py` (tag 2026.10.26):

1. Descarga el asset completo en memoria, verifica SHA-256 contra `SHA2-256SUMS` y escribe `yt-dlp.exe.new`.
2. `os.rename(yt-dlp.exe, yt-dlp.exe.old)` y `os.rename(yt-dlp.exe.new, yt-dlp.exe)`. Windows permite **renombrar** un ejecutable en uso, no sobrescribirlo ni borrarlo. Las instancias ya en ejecución siguen corriendo desde el `.old`.
3. En Windows no borra el `.old` en el momento: registra en `atexit` un `cmd` (`ping ... -n 5 & del /F ".old"`). Si otra instancia sigue usando el `.old`, el `del` falla en silencio y el archivo queda.
4. Al inicio de la siguiente actualización hace `os.remove(old)`; si el `.old` sigue bloqueado, aborta con `Unable to remove the old version`.
5. Con `-U` solo (sin URL), el proceso termina tras actualizar; no se reinicia.

Veredicto: **seguro para los jobs activos** (siguen con la copia vieja), pero **frágil en repeticiones**: un `.old` bloqueado hace fallar el siguiente `-U`, y un `-U` simultáneo con una descarga que arranca puede ver un `yt-dlp.exe` ausente un instante entre los dos `rename`. Se probó `-U` real en macOS desde 2025.11.12 hacia 2026.10.26: reemplaza el binario en su sitio, conserva el nombre y el hash cambia (hay que refrescar `engine.json` después).

Alternativa recomendada (la que ya implica la spec: "si `-U` falla, se reinstala el release"), endurecida:

1. Ejecutar la actualización solo cuando no haya jobs `downloading`/`processing`, bloqueando el despacho de jobs nuevos durante la operación (un lock de Engine).
2. Borrar `yt-dlp.exe.old` y `.new` al arrancar la app y antes de cada actualización.
3. Instalar con el mismo camino que la instalación inicial: descargar a un temporal, verificar contra `SHA2-256SUMS`, y activar con rename-swap (`yt-dlp.exe` a `.old`, nuevo a `yt-dlp.exe`) en lugar de `-U`. Así se controla el hash de `engine.json`, se evita depender de `ping`/`cmd` y no se necesita el binario en uso para actualizarse.
4. Si el rename falla por bloqueo, diferir la actualización (reintento en 24 h o al apagar).

Queda preparado un job `update-windows` en el workflow del spike para observar este comportamiento en un runner real (ver abajo).

## Docker Compose hola mundo

Archivos: `spike/Dockerfile` (python:3.13-slim + `uv`), `spike/compose.yaml`, `spike/app/main.py`, `spike/app/static/index.html`, `spike/pyproject.toml`. `BIND_HOST=0.0.0.0`, `PORT` fijo (se probó 18765), `OPEN_BROWSER=0`, publicación `127.0.0.1:${PORT}:${PORT}`.

- `curl http://127.0.0.1:18765/api/health` devuelve `{"app":"youtube-downloader-spike","version":"0.0.0"}`; `/` sirve el `index.html`; `localhost` también funciona.
- Desde el host contra la IP LAN (`192.168.18.71:18765`): conexión rechazada (curl exit 7). `docker ps` muestra `127.0.0.1:18765->18765/tcp`.
- Nota: `uv sync --no-install-project` con `pyproject.toml` sin `uv.lock` funciona; en el repo real conviene versionar `uv.lock` y usar `uv sync --frozen`.

## GitHub Actions (preparado, no ejecutado)

`spike/.github-workflow-spike-01.yml` (copiar a `.github/workflows/` en una rama de prueba; es `workflow_dispatch`):

- Job `build`, matriz `macos-latest` / `windows-latest`: `astral-sh/setup-uv`, `uv sync --group build --python 3.13`, `pyinstaller --onedir` con `--add-data "app/static<sep>static"` (separador `:` en macOS y `;` en Windows), `--noconsole` en Windows, comprobación `file` de la arquitectura en macOS, arranque con `--no-browser --port 18765`, sondeo de `/api/health` (30 s) y de `/`, y subida del artefacto.
- Job `update-windows`: descarga `yt-dlp.exe` 2025.11.12, mantiene una instancia ocupada con un servidor local lento, ejecuta `-U` y un segundo `--update-to`, mostrando el estado del `.old` y de la instancia viva.
- Riesgos a observar en la primera corrida: que el `.exe` sin consola no cuelgue al arrancar sin stdout; que el arranque en frío de un `.exe` `onedir` supere los 30 s por antivirus; y que `macos-latest` sea arm64 (el paso `file` lo confirma).

## Cambios propuestos a la spec/ADRs

Spec:

1. "Engine" > yt-dlp: indicar la flag exacta `--js-runtimes deno:<ruta absoluta>` (pasar siempre; sin ella `yt-dlp` solo busca `deno` en el `PATH`). Mencionar que el binario oficial ya trae `yt-dlp-ejs`.
2. "Engine" > ffmpeg: fijar proveedor: martin-riedl release 9.0.2 (macOS arm64, Linux arm64/x64, `ffmpeg` y `ffprobe` como zips separados) y Gyan essentials 9.0.2 para Windows x64 (o BtbN con espejo propio). Añadir Linux arm64 (dev en Apple Silicon) además de x64 (CI).
3. "Engine" > Deno: asset `deno-aarch64-unknown-linux-gnu` además del x64; documentar que el `.sha256sum` de Windows está en formato PowerShell.
4. "Engine" > actualización: sustituir "`-U`" en Windows por descarga a temporal + verificación + rename-swap con limpieza de `.old`/`.new`, ejecutada sin jobs activos, o mantener `-U` solo en macOS. Actualizar `engine.json` con el hash nuevo tras cada actualización.
5. "Runner y yt-dlp": todas las invocaciones (incluido el preview) deben pasar `--ffmpeg-location`; sin ella el formato por defecto degrada a `b`.
6. "Runner y yt-dlp": sustituir "Fórmula exacta a confirmar" por la tabla `-S` de este documento. Añadir `-f` de audio: `ba[acodec^=mp4a]/ba` (m4a), `ba[acodec=opus]/ba` (opus), `ba` (mp3), siempre con `-x --audio-quality 0 --audio-format <fmt>`.
7. "Runner y yt-dlp" > Progreso: añadir `--progress-template "postprocess:POSTPROC%(progress)j"`; las líneas `POSTPROC` salen por stderr, las `PROGRESS` por stdout; leer ambos. Documentar los dos streams (video y audio) con dos pasadas a 100 % y el `finished` por stream.
8. "Runner y yt-dlp": el aviso de que un 2160p `.mp4` puede ser VP9 (no H.264) ya está en ADR-0009; sin cambios.
9. "Entorno de desarrollo": versionar `uv.lock` y construir la imagen con `uv sync --frozen`.
10. "Empaquetado": `--add-data` usa `:` en macOS y `;` en Windows; resolver los estáticos con `sys._MEIPASS` al ejecutar empaquetado.

ADR-0002: añadir en Consequences que la fuente Windows de ffmpeg debe ser un release versionado y permanente (Gyan) o un espejo propio, y que los binarios Linux se resuelven para arm64 (dev) y x64 (CI).

ADR-0009: añadir la tabla `-S` y la observación de que, en 1440p/2160p, el orden de fallback observado es VP9 antes que AV1 (por la distancia en la preferencia `vcodec`).

Glosario: ningún cambio.

## Decisiones pendientes para el usuario

1. Proveedor de ffmpeg para Windows: Gyan (recomendado, estable, 109 MB) o BtbN (spec actual, 195 MB, requiere espejo propio para pin estable).
2. Actualización en Windows: `-U` nativo con las limitaciones descritas, o rename-swap propio (recomendado).
3. Qué hacer si falta Deno o falla `deno --version`: bloquear el Engine en `error` (recomendado) o permitir descargas degradadas.
4. Ejecutar el workflow del spike en GitHub (la restricción del encargo prohíbe hacerlo desde aquí).
