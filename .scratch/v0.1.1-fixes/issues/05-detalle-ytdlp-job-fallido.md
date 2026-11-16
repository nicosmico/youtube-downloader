# 05: "Ver detalle" en jobs fallidos

**What to build:** Cada job `failed` muestra un enlace "Ver detalle" que despliega las últimas líneas de salida de `yt-dlp` (stdout y stderr) de su último `Attempt`, para entender por qué falló más allá del mensaje saneado. La salida se guarda acotada por `Attempt` y se descarta con un reintento o al quitar el job del historial. Ver la sección "Registros" de la spec.

**Blocked by:** None (can start immediately).

**Status:** resolved

- [x] El runner guarda las últimas líneas de salida de `yt-dlp` de cada `Attempt`, con un límite fijo.
- [x] Un endpoint devuelve ese detalle para un job; los jobs sin detalle responden de forma clara.
- [x] La tarjeta de un job `failed` muestra "Ver detalle" y lo despliega.
- [x] Reintentar o quitar el job del historial descarta el detalle anterior.
- [x] Tests con `FakeEngine` que falla con stderr conocido, y tests de componente.

## Comments

**2026-11-15**: implementado en la rama `ticket/v011-app` (sin push).

- Almacenamiento: tabla `job_output (job_id PK, attempt, output)` con `ON DELETE CASCADE` (migración 5), en vez de `$DATA_DIR/logs/<job_id>.log`. Razón: el borrado del historial y el reintento ya pasan por el repositorio y la fila desaparece con el job (sin archivos huérfanos ni limpieza al arrancar), es atómico con el cambio de estado y evita rutas y permisos en Windows. Está acotado a 200 líneas de 2000 caracteres como máximo.
- El runner guarda stdout y stderr de `yt-dlp` en orden de llegada, sin las líneas de progreso, solo cuando el `Attempt` falla (código distinto de 0, archivo ausente o fallo al mover), antes de publicar `failed`. Un fallo sin proceso (no arrancó) no guarda nada.
- `GET /api/jobs/{id}/output` → `{attempt, lines}`; `404 job_not_found` o `404 output_unavailable` ("No hay detalle guardado de esta descarga."). `requeue` borra la salida; quitar del historial la borra por cascada.
- Frontend: "Ver detalle" / "Ocultar detalle" en jobs `failed`, ligado al `Attempt` (un fallo posterior no muestra la salida vieja).
- Verificado con `FakeEngine` (nuevos `stdout_lines` y `stderr_lines`) y en la app real con un video borrado: `ERROR: [youtube] aaaaaaaaaaa: This video is unavailable`.

**2026-11-15 — Resuelto.** Publicado en `v0.1.1` (Native/Release `43782090965`, CI `43782088015`).
