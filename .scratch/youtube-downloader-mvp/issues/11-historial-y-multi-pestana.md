# 11: Historial, multi-pestaña e Idle Shutdown

**What to build:** El `History` muestra los jobs en estado terminal y sobrevive al reinicio; la `Queue` muestra los que están en espera o en curso. El usuario puede quitar un job del `History` sin borrar el archivo, abrir la carpeta de descargas y mostrar en Finder/Explorer el archivo de un job completado. Varias pestañas comparten el mismo estado por SSE, y al reconectar se rehidrata desde la API. Un cliente lento no bloquea al runner ni a otros clientes. La app se cierra sola tras 10 minutos sin pestañas conectadas y con la `Queue` vacía.

**Blocked by:** 10 (Cancelar y reintentar).

**Status:** ready-for-agent

- [ ] El `History` sobrevive al reinicio y separa terminales de jobs en cola o en curso.
- [ ] Quitar un job del `History` no borra el archivo; quitar uno no terminal responde `409`.
- [ ] `POST /api/jobs/{id}/reveal` responde para jobs `completed`; la apertura nativa se valida en el ticket 14.
- [ ] Dos pestañas abiertas muestran el mismo estado en vivo.
- [ ] Al reconectar, la pestaña recupera el estado con `GET /api/jobs`.
- [ ] Un cliente lento no bloquea al runner ni a otros clientes.
- [ ] Sin clientes SSE, sin jobs pendientes ni activos y sin instalación del Engine en curso, la app se apaga tras 10 minutos y emite `shutdown` con motivo `idle`; cualquier conexión reinicia el temporizador.
- [ ] Tests de SSE, reconexión, rehidratación e `Idle Shutdown` con reloj inyectable.
