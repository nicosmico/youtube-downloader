# 01: Backend — carpeta de descargas configurable

**What to build:** El backend de la spec `../spec.md` (léela entera, sobre todo la sección "API", que es el contrato con el frontend) y del ADR `docs/adr/0012-carpeta-de-descargas-configurable.md`.

**Blocked by:** None.

**Status:** ready-for-agent

## Diseño

- **Persistencia:** migración nueva en `backend/app/db.py` (sigue el patrón de `MIGRATIONS`):
  - tabla `settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)`;
  - columna `jobs.download_dir TEXT` (nullable: los jobs viejos usan la de por defecto).
- **Valor por defecto:** el `download_dir` de `config.py` (`DOWNLOAD_DIR` o `~/Downloads`), como hoy. El efectivo es el guardado en `settings` o el de por defecto.
- **Un módulo pequeño** (p. ej. `backend/app/download_dir.py` o en `jobs/`) con un objeto que lea, valide, guarde y restablezca la carpeta y produzca el dict del `GET`. Lo usan la API, la Queue al encolar y `open-downloads`. Validación: ruta absoluta, existe, es directorio y se puede escribir (crear y borrar un archivo temporal).
- **Al encolar** (`JobQueue.enqueue` / `enqueue_batch`, o en `jobs/api.py`): cada job guarda la carpeta efectiva en `download_dir`. Si es una carpeta elegida y no existe, 409 `download_dir_unavailable` (la de por defecto se crea al mover, como hoy). Un reintento (`requeue`) conserva la carpeta del job.
- **Al mover** (`runner.py` `_destination` / `FileMover.move`): la carpeta base es la del job (o la de por defecto si es `NULL`). `FileMover` hoy tiene una `download_dir` fija: pásale la base por llamada. Si la base no es la de por defecto y no existe en el momento de mover, el job falla con un fallo nuevo en `jobs/failures.py`, "La carpeta de descargas no está disponible." (no se crea). Las subcarpetas de playlist se siguen creando.
- **Selector nativo** inyectable (un `Callable[[Path | None], Path | None]`, como `FileRevealer` en `opener.py`), con `start` en la carpeta actual:
  - macOS: `osascript -e 'POSIX path of (choose folder with prompt "Elige la carpeta de descargas" default location (POSIX file "<actual>"))'`. Cancelar sale con código distinto de 0 y "User canceled" (-128) en stderr → `None`. Escapa la ruta para AppleScript.
  - Windows: `powershell -NoProfile -STA -Command` con `System.Windows.Forms.FolderBrowserDialog` (`SelectedPath` inicial, `ShowNewFolderButton = $true`). Para que salga delante del navegador, pásale como dueño un `Form` con `TopMost = $true`. Imprime la ruta elegida o nada. `CREATE_NO_WINDOW`. Pasa la ruta inicial por variable de entorno o argumento, nunca interpolada sin escapar en el script.
  - Otros sistemas: excepción que la API convierte en 501 `picker_unavailable`.
  - Un lock: un segundo `choose` mientras hay un diálogo abierto devuelve 409 `picker_busy`.
- **Rutas:** `GET/PUT/DELETE /api/settings/download-dir` y `POST /api/settings/download-dir/choose`, en un router nuevo (p. ej. `backend/app/settings_api.py`), montado en `main.py` como los demás. El `POST choose` y el `PUT` deben ser `def` (hilo de FastAPI), no `async`.
- **SSE:** `settings.updated` en `events.py`, con el dict del `GET`.
- **`open-downloads`** (`backend/app/api.py`): abre la carpeta efectiva; crea solo la de por defecto si falta; si una elegida no existe, 409 `download_dir_unavailable`.
- **`/api/health`** no cambia.
- Actualiza `GLOSSARY.md` si define "Destination"/"Destino" (que ahora es configurable) y la línea de ADR-0007 que dice "sin selector de carpeta" (añade "Sustituido en parte por ADR-0012").

## Acceptance criteria

- [ ] Migración con `settings` y `jobs.download_dir`; los jobs existentes siguen funcionando.
- [ ] Los cuatro endpoints y el evento SSE según el contrato de la spec, con tests (selector falso: elegida, cancelada, no disponible, ocupado; validación del `PUT`).
- [ ] Encolar guarda la carpeta; cambiarla no afecta a lo encolado; un reintento conserva la suya. Tests.
- [ ] 409 al encolar con una carpeta elegida que no existe; fallo claro si desaparece antes de mover. Tests.
- [ ] `open-downloads` abre la carpeta configurada.
- [ ] Tests del comando de cada sistema sin lanzar procesos (como `test_opener.py`): argumentos, escape de la ruta, cancelación.
- [ ] `docker compose run --rm tests`, `ruff check .`, `ruff format --check .`.

## Comments
