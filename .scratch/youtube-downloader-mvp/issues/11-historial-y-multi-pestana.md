# 11: Historial y multi-pestaña

**What to build:** El historial muestra los jobs con su estado final y sobrevive al reinicio. El usuario puede borrar una entrada sin borrar el archivo descargado y abrir la carpeta de descargas. Varias pestañas comparten el mismo estado por SSE, y al reconectar se rehidrata desde la API. Un cliente lento no bloquea al runner ni a otros clientes.

**Blocked by:** 10 (Cancelar y reintentar).

**Status:** ready-for-agent

- [ ] El historial sobrevive al reinicio.
- [ ] Borrar una entrada del historial no borra el archivo.
- [ ] Dos pestañas abiertas muestran el mismo estado en vivo.
- [ ] Al reconectar, la pestaña recupera el estado con `GET /api/jobs`.
- [ ] Un cliente lento no bloquea al runner ni a otros clientes.
- [ ] Tests de SSE, reconexión y rehidratación.
