# 01: yt-dlp sin empaquetar en macOS y Windows

**What to build:** El preview tarda unos 18 s porque `yt-dlp_macos` (y `yt-dlp.exe`) son ejecutables PyInstaller de un solo archivo: cada ejecución se descomprime en una carpeta temporal nueva y el sistema la revisa antes de cargarla (unos 15 s en un Mac real, con 0 % de CPU). yt-dlp publica también la versión sin empaquetar, que tras la primera ejecución arranca en 0,15 s (medido: preview completo de 18 s a 2 s). El Engine debe instalar y actualizar esa versión en macOS y Windows.

**Blocked by:** None.

**Status:** resolved

## Datos verificados (release 2026.10.26)

- Assets: `yt-dlp_macos.zip` y `yt-dlp_win.zip`, ambos con hash en `SHA2-256SUMS` (los mismos que ya usa `_latest_ytdlp`).
- `yt-dlp_macos.zip` (54 MB, 162 entradas): en la raíz, el ejecutable `yt-dlp_macos` y la carpeta `_internal/`. Sin enlaces simbólicos. 107 archivos con bit de ejecución en `external_attr` (`create_system` 3): **`zipfile` no conserva los permisos**, hay que restaurarlos (al menos el ejecutable y las `.so`/`.dylib`/`Python` que lo tengan; lo más simple es aplicar el modo del `external_attr` cuando tiene bits de ejecución).
- `yt-dlp_win.zip` (146 entradas): `yt-dlp.exe` y `_internal/`. Sin permisos que restaurar.
- Linux (`yt-dlp_linux`, `yt-dlp_linux_aarch64`) sigue como hoy: binario único. Es solo el Docker de desarrollo.

## Diseño

- `backend/app/engine/sources.py`: por plataforma, el asset de yt-dlp pasa a ser el zip en macOS y Windows, con el nombre del ejecutable dentro (`yt-dlp_macos`, `yt-dlp.exe`). Linux sin cambios.
- Disposición en disco: una carpeta propia, p. ej. `bin/yt-dlp-dist/` (el nombre no puede ser `bin/yt-dlp`, que es el binario de las instalaciones existentes). `binary_path("yt-dlp")` devuelve el ejecutable dentro de esa carpeta en macOS/Windows; el resto del código (`ytdlp_base_args`, runner, `_check_version`) no cambia.
- Instalación: descargar el zip a un temporal en `bin/`, comprobar el SHA-256 del zip, extraerlo a `bin/yt-dlp-dist.new/` **rechazando rutas absolutas o con `..`** (zip slip), restaurar los permisos, y activarlo con un `os.replace` de la carpeta. Registrar en `engine.json` el `archiveSha256` del zip (no hay un único archivo que hashear).
- `_installed("yt-dlp")`: en macOS/Windows exige que el ejecutable exista en la carpeta nueva **y** que el manifiesto tenga `archiveSha256`. Así una instalación existente (binario `bin/yt-dlp` o `bin/yt-dlp.exe`, sin `archiveSha256`) se considera no instalada y se reinstala sola al arrancar. Tras instalar, borrar el binario viejo si existe (en Windows puede estar bloqueado: ignorar el error, se borra en el siguiente arranque).
- Actualización (`_update_ytdlp`): mismo esquema que hoy con carpetas: extraer en `yt-dlp-dist.new/`, `os.replace` actual → `yt-dlp-dist.old/`, nueva → actual, `_check_version`, y rollback si falla. Borrar `.old` con `shutil.rmtree` ignorando errores. La actualización ya se aplaza mientras haya descargas (`DEFERRED`), así que en Windows no debería haber archivos bloqueados; si el rename falla, error claro y rollback, como hoy.
- `cleanup_leftovers`: además de archivos, borra carpetas `*.new`/`*.old`/`*.tmp` de `bin/` con `rmtree`.
- El primer arranque tras instalar o actualizar es lento (el sistema revisa la carpeta una vez): ya ocurre dentro de `_verify`/`_check_version`, con el Engine en `installing`. No hay que hacer nada más, pero comprobar que `_check_version` no tiene un timeout menor de ~60 s.
- `ENGINE_BIN_DIR` (externo) sin cambios: sigue buscando `yt-dlp`/`yt-dlp.exe` en la carpeta indicada.
- Actualizar `docs/adr/0002-motor-externo-autogestionado.md` con una línea: en macOS y Windows se usa la versión sin empaquetar, y por qué (arranque de 15 s por la extracción y la revisión del sistema).

## Acceptance criteria

- [x] macOS y Windows instalan el zip sin empaquetar, verificado por el SHA-256 del zip, con los permisos restaurados en macOS.
- [x] Extracción segura: una entrada con `..` o ruta absoluta hace fallar la instalación con `EngineError` y no deja nada a medias.
- [x] Una instalación existente con el binario único se migra sola al arrancar y el binario viejo se borra.
- [x] La actualización de yt-dlp cambia la carpeta entera, con rollback si la versión nueva no arranca.
- [x] `cleanup_leftovers` borra carpetas `.new`/`.old` sobrantes.
- [x] Linux sin cambios de comportamiento.
- [x] Tests en `backend/tests/test_engine_manager.py` y `test_engine_sources.py` con zips falsos construidos en el test (sin red), siguiendo los fakes existentes (`fake_engine.py`, `fakes.py`).
- [x] `docker compose run --rm tests`, `ruff check .` y `ruff format --check .` pasan.
- [x] ADR-0002 actualizado.

## Comments

### 2026-11-16 — implementación (agente)

- `sources.py`: en macOS y Windows `ytdlp_asset` pasa a `yt-dlp_macos.zip` / `yt-dlp_win.zip`; nuevos `ytdlp_unpackaged`, `ytdlp_executable` y `YTDLP_DIST_DIR = "yt-dlp-dist"`. Linux igual.
- `manager.py`: `binary_path("yt-dlp")` apunta al ejecutable dentro de `bin/yt-dlp-dist/` (no con `ENGINE_BIN_DIR`). Instalación: zip a temporal, SHA-256 del zip contra `SHA2-256SUMS`, extracción a `yt-dlp-dist.new/` (rechaza rutas absolutas, con `..`, con unidad de Windows o que salgan de la carpeta; restaura los bits de ejecución del `external_attr` en posix), `os.replace` de la carpeta, `archiveSha256` en `engine.json`. `_installed("yt-dlp")` exige `archiveSha256` en macOS/Windows: un binario viejo se migra solo y se borra (error ignorado si está bloqueado; se reintenta en el siguiente arranque). `_update_ytdlp` cambia la carpeta entera con `.new`/`.old` y rollback (borra la carpeta nueva antes de restaurar). `cleanup_leftovers` borra también carpetas `*.new`/`*.old`/`*.tmp`.
- Timeout: `TIMEOUT_SECONDS` (30 s, `engine/io.py`) también es el timeout de red del `UrllibFetcher`, así que no se tocó; `_check_version` ahora pasa `VERSION_CHECK_TIMEOUT_SECONDS = 90` al runner. El timeout del preview (`PREVIEW_TIMEOUT_SECONDS = 30`) no se tocó: la primera ejecución lenta ya ocurre dentro de `_verify`.
- Tests: fakes con zips (`make_zip` con modos, `ytdlp_zip`, `publish_ytdlp(archive=...)`, `FakeRunner.timeouts`); `TestUnpackagedYtdlp` (macOS y Windows) en `test_engine_manager.py` y casos nuevos en `test_engine_sources.py`. ADR-0002 actualizado.
- Pendiente: la prueba real de punta a punta es el smoke test empaquetado de CI en macOS y Windows (no se ejecutó aquí).

**2026-11-17 — Resuelto.** Publicado en `v0.2.4`. El orquestador extrajo el `yt-dlp_macos.zip` real con `_extract_zip` (en Docker) y lo ejecutó en un Mac: 14 s la primera vez y 0,15 s las siguientes. El smoke empaquetado de CI instaló el Engine con el zip nuevo en macOS y Windows.
