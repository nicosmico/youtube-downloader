# 02: Walking skeleton

**What to build:** El ejecutable arranca, elige un puerto libre, sirve el shell de Angular, escribe `runtime.json`, abre el navegador y expone `/api/health`. Una segunda ejecución reutiliza la instancia existente. La UI incluye un botón para cerrar la aplicación de forma ordenada. Desde este ticket se aplican la validación de `Host` local y la cabecera requerida en endpoints mutantes.

**Blocked by:** 01 (Spike — Engine y empaquetado).

**Status:** ready-for-agent

- [ ] Ejecutar la app abre el navegador con el shell de Angular.
- [ ] Una segunda ejecución abre la instancia existente y termina sin levantar otro servidor.
- [ ] `/api/health` responde versión, estado del Engine y puerto.
- [ ] "Cerrar aplicación" apaga el servidor y elimina `runtime.json`.
- [ ] Peticiones con `Host` no local o mutaciones sin la cabecera de la app son rechazadas.
- [ ] Tests de integración verdes sin red.
