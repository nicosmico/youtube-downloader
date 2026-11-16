# 01: Idle Shutdown rápido tras cerrar la pestaña

**What to build:** `Idle Shutdown` pasa a 15 s tras desconectarse el último cliente SSE (nuevo valor por defecto de `IDLE_SHUTDOWN_SECONDS`), con 60 s de gracia al arrancar hasta que se conecta la primera pestaña. Las condiciones de inactividad no cambian y `0` sigue desactivándolo. El smoke test empaquetado fija un `IDLE_SHUTDOWN_SECONDS` alto para no cerrarse entre pasos, y gana un caso que comprueba el cierre automático tras abrir y cerrar una conexión SSE con un timeout pequeño. Actualizar `GLOSSARY.md` (`Idle Shutdown`) y el ADR-0001; el README lo actualiza el orquestador. Ver la spec, sección "Idle Shutdown rápido".

**Blocked by:** None (can start immediately).

**Status:** ready-for-agent

- [ ] Cierre unos 15 s después de cerrar la última pestaña, sin descargas ni trabajo del motor.
- [ ] 60 s de gracia al arrancar sin ninguna pestaña.
- [ ] Una reconexión antes del plazo (recarga) cancela el cierre.
- [ ] Con descargas activas no se cierra; empieza a contar al vaciarse la `Queue`.
- [ ] `IDLE_SHUTDOWN_SECONDS=0` lo desactiva.
- [ ] Smoke test: entorno con timeout alto (también en `--reopen`) y caso nuevo de cierre automático.
- [ ] Tests de `IdleMonitor` con reloj inyectado; glosario y ADR-0001 actualizados.

## Comments
