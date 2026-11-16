# 02: Relevo de versión en Single Instance

**What to build:** `probe_health` también devuelve la `version` de la instancia en marcha. En `acquire_instance`:
- Si la instancia sana tiene una versión menor que la propia, o no informa versión: se le envía `POST /api/system/shutdown` (con `X-Requested-With: youtube-downloader`), se espera hasta unos 15 s a que suelte `instance.lock` y se sigue como `Start`.
- Si es igual o mayor: `Reuse`, como hoy.
- Si la vieja no se cierra a tiempo: aviso en el log y `Reuse`.

La comparación usa `app.updates.is_newer`. Se registra en el log "Taking over from version X (running Y)". No editar el README; lo hace el orquestador. Ver la spec, sección "Relevo de versión".

**Blocked by:** None (can start immediately).

**Status:** ready-for-agent

- [x] Versión menor o sin versión: cierre pedido y `Start` cuando se libera el lock.
- [x] Misma versión o mayor: `Reuse`.
- [x] Si la vieja no se cierra a tiempo: `Reuse` con aviso en el log.
- [x] El cierre se pide con la cabecera correcta y solo a `127.0.0.1`.
- [x] Tests con `probe` y `shutdown` falsos y sin red; `ruff check` y `ruff format --check` limpios.

## Comments

2026-11-16 (agente): Hecho en `backend/app/single_instance.py`. `probe_health` ahora devuelve `Health(version)` o `None` (no es esta app); `Probe = Callable[[int], Health | None]`. Nuevo `request_shutdown(port)` (POST a `127.0.0.1:<port>/api/system/shutdown` con `X-Requested-With: youtube-downloader`, sin Origin; los errores se registran y no se propagan). `acquire_instance` gana los parámetros inyectables `shutdown`, `own_version` y `takeover_attempts` (60 x 0.25 s = 15 s). Misma versión o mayor: `Reuse`. Menor, sin versión o ilegible: log "Taking over from version X (running Y)", pide el cierre, espera el lock, borra `runtime.json` y `Start`. Si no se libera a tiempo: aviso y `Reuse`. Cubre los dos caminos (lock libre pero instancia sana respondiendo, y lock en manos de otro proceso). `launcher.py` no cambia: ya abre el navegador en `Start`. GLOSSARY (Single Instance) actualizado. Sin desvíos de la spec; un detalle: con el lock libre y una vieja respondiendo no se espera a que la vieja deje de responder, solo se sigue como `Start` tras pedir el cierre (caso de sistemas de archivos sin locks; el puerto lo asigna el SO). Verificado: `docker compose run --rm tests` (731 passed), `ruff check` y `ruff format --check` limpios; el helper `request_shutdown` se prueba contra un servidor HTTP local en 127.0.0.1.
