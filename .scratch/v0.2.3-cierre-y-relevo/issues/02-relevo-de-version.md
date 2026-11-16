# 02: Relevo de versión en Single Instance

**What to build:** `probe_health` también devuelve la `version` de la instancia en marcha. En `acquire_instance`:
- Si la instancia sana tiene una versión menor que la propia, o no informa versión: se le envía `POST /api/system/shutdown` (con `X-Requested-With: youtube-downloader`), se espera hasta unos 15 s a que suelte `instance.lock` y se sigue como `Start`.
- Si es igual o mayor: `Reuse`, como hoy.
- Si la vieja no se cierra a tiempo: aviso en el log y `Reuse`.

La comparación usa `app.updates.is_newer`. Se registra en el log "Taking over from version X (running Y)". No editar el README; lo hace el orquestador. Ver la spec, sección "Relevo de versión".

**Blocked by:** None (can start immediately).

**Status:** ready-for-agent

- [ ] Versión menor o sin versión: cierre pedido y `Start` cuando se libera el lock.
- [ ] Misma versión o mayor: `Reuse`.
- [ ] Si la vieja no se cierra a tiempo: `Reuse` con aviso en el log.
- [ ] El cierre se pide con la cabecera correcta y solo a `127.0.0.1`.
- [ ] Tests con `probe` y `shutdown` falsos y sin red; `ruff check` y `ruff format --check` limpios.

## Comments
