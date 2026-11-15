# 14: Smoke de empaquetado nativo

**What to build:** En cuanto existe la primera descarga end-to-end, construir el producto real (no un "hola mundo") con PyInstaller en GitHub Actions para macOS arm64 y Windows x64, y verificar en los runners que el ejecutable prepara el Engine y descarga un video. El objetivo es descubrir pronto los problemas de PyInstaller, rutas, subprocesos y binarios nativos; el pulido de distribución queda para los tickets 12 y 13.

**Blocked by:** 05 (Descarga de un video end-to-end).

**Status:** resolved

- [x] El workflow construye el `onedir` en `macos-latest` y `windows-latest` con el build de Angular incluido, y publica artefactos de prueba.
- [x] En cada runner, el ejecutable arranca con `--no-browser`, responde `/api/health` y llega a Engine `ready`.
- [x] Un smoke con red descarga un video corto de YouTube desde el ejecutable: verificado en un Mac real (arm64). En los runners de GitHub YouTube bloquea la IP con su verificación anti-bot; el smoke lo detecta por el mensaje exacto y lo marca como aviso. Windows queda sin descarga real verificada hasta el ticket 13.
- [x] "Abrir carpeta" usa `open` en macOS y `explorer` en Windows; se verifica al menos que el comando se invoca sin error.
- [x] Los problemas encontrados quedan documentados o resueltos antes de seguir con el ticket 06.

## Comments

**2026-11-15 — Implementación.** `packaging/youtube-downloader.spec` (PyInstaller `onedir`, entry `packaging/entry.py` = Launcher, estáticos de Angular como `datas` con la forma de tupla, sin separador; `console=False` en Windows; `collect_submodules("uvicorn")`), `packaging/smoke.py` (solo stdlib: arranca el exe con `--no-browser` y `DATA_DIR`/`DOWNLOAD_DIR` temporales, lee el puerto de `runtime.json`, `/api/health`, `GET /` sirve Angular, Engine `ready`, `open-downloads` 200, descarga de `jNQXAC9IVRw`, `shutdown` y comprobación de que el proceso sale y `runtime.json` desaparece; vuelca `app.log` si falla) y `.github/workflows/native.yml` (matriz macOS/Windows; `push` a `main` y `ticket/14-*`, `pull_request`, `workflow_dispatch`). PyInstaller entra como grupo de dependencias `build` en `backend/pyproject.toml` (`uv.lock` actualizado; la imagen de desarrollo no lo instala).

Resultado (run `43759477328`): ambos jobs verdes. `onedir` de 33 MB en ambos; artefactos subidos de 24 MB (macOS arm64, confirmado con `file`) y 18 MB (Windows x64); build completo en 45 s (macOS) y 80 s (Windows). El exe sin consola arranca y responde en ~1 s; el Engine llega a `ready` en ~5 s (macOS) y ~8 s (Windows) con descarga y SHA-256 reales (yt-dlp 2026.10.26, ffmpeg/ffprobe 9.0.2, Deno 2.9.8). `open-downloads` responde 200 en ambos (`open` / `explorer`). El apagado por `POST /api/system/shutdown` termina el proceso con código 0 y borra `runtime.json`.

Descarga de red: **bloqueada por el bot check de YouTube** en ambos runners ("Sign in to confirm you're not a bot"; el job falla con el mensaje "YouTube bloqueó temporalmente..."). No se intenta saltar. El smoke distingue ese caso (código de salida 10) y el workflow lo convierte en un `::warning::`; cualquier otro fallo de descarga sí pone el job en rojo. Por eso el tercer punto queda sin marcar: la descarga real desde el ejecutable empaquetado se verificó hasta que `yt-dlp` contacta con YouTube (Deno, ffmpeg y rutas del Engine funcionan), pero falta un runner con IP no bloqueada o una prueba manual local con el exe.

Bugs de producto encontrados: ninguno; no se tocó el código de la app. Observaciones: PyInstaller avisa `Hidden import "tzdata" not found` (inofensivo). El smoke no puede comprobar que Finder/Explorer se abra visualmente, solo que el comando no falla.


**2026-11-15 — Revisión del orquestador.** El artefacto de macOS (run `43759663183`) falló en un Mac real con `CERTIFICATE_VERIFY_FAILED`: el OpenSSL del Python empaquetado no trae certificados fuera de los runners. Corregido con `truststore` (respaldo `certifi`) y un segundo smoke en CI con el almacén de certificados de OpenSSL vacío. La consulta de la última versión de `yt-dlp` pasó a la redirección pública de GitHub, sin `api.github.com` ni `GITHUB_TOKEN`. Artefacto final (run `43760895171`) probado en el Mac: Engine `ready`, "Me at the zoo.mp4" descargado y apagado con exit 0. CI `43760895232` verde.

**2026-11-15 — Resuelto.** Native verde sobre `main` (run `43761261417`, lanzado a mano porque el último commit era solo de documentación).
