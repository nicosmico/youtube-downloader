# 02: API para quitar una playlist y vaciar el historial

**What to build:** En el backend:
- `DELETE /api/batches/{batch_id}`: quita los jobs terminales del Batch.
- `DELETE /api/history`: quita todos los jobs terminales.

Las dos son atómicas (`DELETE … AND status IN (terminales) RETURNING id`), borran los Batches que quedan vacíos, responden `{"removed": n}` y, si `n > 0`, publican un único evento SSE `jobs.removed` con `{"ids": [...]}`. Un Batch inexistente da `404 batch_not_found`. No tocan archivos en disco.

Ver la spec, sección "Quitar una playlist y vaciar el historial", parte Backend.

**Blocked by:** None (can start immediately).

**Status:** ready-for-agent

- [ ] Solo se quitan jobs terminales; los que están en curso se quedan.
- [ ] El Batch se borra cuando queda sin jobs; `job_output` se borra en cascada.
- [ ] `jobs.removed` se publica una vez con los ids, y nunca con `n = 0`.
- [ ] `404 batch_not_found` para un Batch desconocido.
- [ ] Los archivos descargados no se tocan.
- [ ] Tests de repositorio, cola y API; `ruff check` y `ruff format --check` limpios.

## Comments
