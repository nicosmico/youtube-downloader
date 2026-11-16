# 05: Datos de desarrollo en un volumen de Docker

**What to build:** En `compose.yaml`, el directorio de datos de la app pasa a un volumen de Docker en lugar de `./.dev-data`, para que SQLite en modo WAL no corra sobre una carpeta compartida con el host (la base de datos apareció corrupta con la cabecera a ceros). Los binarios del Engine pueden seguir en una carpeta del host mediante `ENGINE_BIN_DIR` para no descargarlos de nuevo. Documentar en el README cómo inspeccionar o borrar el volumen. Solo afecta al desarrollo. Ver la spec, sección "Base de datos de desarrollo".

**Blocked by:** None (can start immediately).

**Status:** resolved

- [x] `docker compose up` usa un volumen para `DATA_DIR`; reiniciar el contenedor conserva el historial.
- [x] El Engine no se vuelve a descargar entre reinicios.
- [x] Varias sesiones seguidas de `up`/`down`/`restart` no corrompen la base de datos.
- [x] README actualizado (incluido cómo resetear el volumen).

## Comments

2026-11-15: Hecho. `compose.yaml` monta el volumen nombrado `ytdl-dev-data` en `/data`; `HOST_DOWNLOAD_DIR` sigue siendo un bind mount. Los binarios del Engine NO usan `ENGINE_BIN_DIR` (desactiva descarga, actualización y hashes por diseño, ADR-0008): `/data/bin` vive dentro del mismo volumen, así que se descargan una sola vez y se siguen actualizando y verificando con normalidad. Se retira `HOST_DATA_DIR`.

Verificado con `PORT=8775`: Engine instalado una vez (`ready`), job de audio m4a creado; 3 ciclos `down`/`up` y 3 `restart`: Engine `ready` sin redescarga, el historial se conserva y `PRAGMA integrity_check` = `ok` en todos. Después `down -v` y se borró el material de prueba. README actualizado (sección "Datos de desarrollo (volumen)": inspeccionar, copiar, resetear; `.dev-data/` ya no se usa).

**2026-11-16 — Resuelto.** Publicado en `v0.2.0` (Native/Release `43878583896`, CI `43878578070`), tras la revisión visual del orquestador en claro, oscuro y 320 px.
