# 05: Datos de desarrollo en un volumen de Docker

**What to build:** En `compose.yaml`, el directorio de datos de la app pasa a un volumen de Docker en lugar de `./.dev-data`, para que SQLite en modo WAL no corra sobre una carpeta compartida con el host (la base de datos apareció corrupta con la cabecera a ceros). Los binarios del Engine pueden seguir en una carpeta del host mediante `ENGINE_BIN_DIR` para no descargarlos de nuevo. Documentar en el README cómo inspeccionar o borrar el volumen. Solo afecta al desarrollo. Ver la spec, sección "Base de datos de desarrollo".

**Blocked by:** None (can start immediately).

**Status:** ready-for-agent

- [ ] `docker compose up` usa un volumen para `DATA_DIR`; reiniciar el contenedor conserva el historial.
- [ ] El Engine no se vuelve a descargar entre reinicios.
- [ ] Varias sesiones seguidas de `up`/`down`/`restart` no corrompen la base de datos.
- [ ] README actualizado (incluido cómo resetear el volumen).
