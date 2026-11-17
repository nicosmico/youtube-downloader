# 01: yt-dlp sin empaquetar en macOS y Windows

**What to build:** El preview tarda unos 18 s porque `yt-dlp_macos` (y `yt-dlp.exe`) son ejecutables PyInstaller de un solo archivo: cada ejecución se descomprime en una carpeta temporal nueva y el sistema la revisa antes de cargarla (unos 15 s en un Mac real, con 0 % de CPU). yt-dlp publica también la versión sin empaquetar, que tras la primera ejecución arranca en 0,15 s (medido: preview completo de 18 s a 2 s). El Engine debe instalar y actualizar esa versión en macOS y Windows.

**Blocked by:** None.

**Status:** ready-for-agent

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

- [ ] macOS y Windows instalan el zip sin empaquetar, verificado por el SHA-256 del zip, con los permisos restaurados en macOS.
- [ ] Extracción segura: una entrada con `..` o ruta absoluta hace fallar la instalación con `EngineError` y no deja nada a medias.
- [ ] Una instalación existente con el binario único se migra sola al arrancar y el binario viejo se borra.
- [ ] La actualización de yt-dlp cambia la carpeta entera, con rollback si la versión nueva no arranca.
- [ ] `cleanup_leftovers` borra carpetas `.new`/`.old` sobrantes.
- [ ] Linux sin cambios de comportamiento.
- [ ] Tests en `backend/tests/test_engine_manager.py` y `test_engine_sources.py` con zips falsos construidos en el test (sin red), siguiendo los fakes existentes (`fake_engine.py`, `fakes.py`).
- [ ] `docker compose run --rm tests`, `ruff check .` y `ruff format --check .` pasan.
- [ ] ADR-0002 actualizado.

## Comments
