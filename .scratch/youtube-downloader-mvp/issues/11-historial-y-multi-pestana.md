# 11: Historial, multi-pestaña e Idle Shutdown

**What to build:** El `History` muestra los jobs en estado terminal y sobrevive al reinicio; la `Queue` muestra los que están en espera o en curso. El usuario puede quitar un job del `History` sin borrar el archivo, abrir la carpeta de descargas y mostrar en Finder/Explorer el archivo de un job completado. Varias pestañas comparten el mismo estado por SSE, y al reconectar se rehidrata desde la API. Un cliente lento no bloquea al runner ni a otros clientes. La app se cierra sola tras 10 minutos sin pestañas conectadas y con la `Queue` vacía.

**Blocked by:** 10 (Cancelar y reintentar).

**Status:** ready-for-agent

- [x] El `History` sobrevive al reinicio y separa terminales de jobs en cola o en curso.
- [x] Quitar un job del `History` no borra el archivo; quitar uno no terminal responde `409`.
- [x] `POST /api/jobs/{id}/reveal` responde para jobs `completed`; la apertura nativa se valida en el ticket 14.
- [x] Dos pestañas abiertas muestran el mismo estado en vivo.
- [x] Al reconectar, la pestaña recupera el estado con `GET /api/jobs`.
- [x] Un cliente lento no bloquea al runner ni a otros clientes.
- [x] Sin clientes SSE, sin jobs pendientes ni activos y sin instalación del Engine en curso, la app se apaga tras 10 minutos y emite `shutdown` con motivo `idle`; cualquier conexión reinicia el temporizador.
- [x] Tests de SSE, reconexión, rehidratación e `Idle Shutdown` con reloj inyectable.

## Comments

- 2026-11-15: Implementado en la rama `ticket/11-history`.
  - **Historial/Queue:** la UI separa "En curso" (`queued`/`downloading`/`processing`) de "Historial" (terminales) con `GET /api/jobs?status=…`; el Historial pagina con `before` ("Cargar más"). Al (re)conectar se piden dos listas (Queue completa y primera página del Historial); las páginas extra cargadas se descartan. Un `Batch` con jobs en ambos grupos aparece en las dos secciones.
  - **Quitar:** `DELETE /api/jobs/{id}` solo para terminales (`409 job_not_removable`), nunca toca el archivo, emite `job.removed {id}` y borra el `Batch` con su último job. No se implementó "Limpiar historial" (no está en la spec de la API).
  - **Reveal:** `POST /api/jobs/{id}/reveal` (`open -R` / `explorer /select,`). Errores: `404 file_missing`, `409 job_not_completed`, `501 open_unavailable`, `500 open_failed`. `/api/health` ahora incluye `platform` para rotular el botón (Finder/Explorador/neutral). La apertura nativa real queda para el ticket 14.
  - **Cliente lento:** `publish` nunca bloquea (`call_soon_threadsafe` + `put_nowait`); con la cola por cliente llena se descarta a ese cliente (su stream termina, el navegador reconecta y rehidrata). Cubierto con tests sobre el broadcaster real.
  - **Idle Shutdown:** `app/idle.py` (`IdleMonitor`, reloj inyectable). Sin clientes, sin trabajo (Queue o Engine) durante `IDLE_SHUTDOWN_SECONDS` (600 por defecto, 0 desactiva). Cualquier evento publicado, conexión o desconexión reinicia el temporizador. Emite `shutdown {reason: "idle"}` y hace el apagado ordenado. La UI muestra "La aplicación se cerró por inactividad".
  - **Verificación real (Docker, `IDLE_SHUTDOWN_SECONDS=20`):** con un cliente SSE conectado no se apagó en 40 s; tras cerrarlo y sin jobs se apagó en ~20 s (exit 0); tras terminar un job sin clientes se apagó ~20 s después. `DELETE` dejó el archivo en disco; `reveal` respondió `501 open_unavailable` en Docker.
  - **Nota:** en Docker Desktop una pestaña abierta (o el proxy de puertos) mantiene viva la conexión SSE hacia el contenedor aunque el cliente muera, así que el apagado por inactividad no se dispara mientras haya una pestaña del navegador apuntando a la app; es el comportamiento buscado.
  - **Fuera de alcance:** el evento `shutdown` con motivos `user` y `signal` no se emite todavía (la UI ya los trata como cierre normal).

**2026-11-15 — Revisión del orquestador.** Checks repetidos (679 backend ×2, 213 frontend, ruff, build). El cierre desde la UI no avisaba a las demás pestañas (solo se emitía `shutdown` con `idle`): ahora el botón publica `shutdown {reason: "user"}`, con test. Probado en el navegador integrado con dos pestañas: secciones e historial correctos, y al pulsar "Cerrar aplicación" en una, la otra muestra "La aplicación se cerró". Spec actualizada con códigos de `reveal`/`DELETE`, `platform` en `/api/health`, `IDLE_SHUTDOWN_SECONDS` y los motivos de `shutdown`.
