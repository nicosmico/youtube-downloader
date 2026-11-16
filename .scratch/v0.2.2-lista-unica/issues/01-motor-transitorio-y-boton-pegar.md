# 01: Estado transitorio del motor y botón "Pegar"

**What to build:** En el preview (`frontend/src/app/preview/`):
- El motor en estado `null`, `missing` o `installing` deja de mostrarse como error. Con `null` o `missing` no se muestra nada; con `installing`, un aviso neutro "Preparando el motor…" con indicador de actividad.
- El rojo queda solo para `error`.
- Un enlace pegado mientras el motor no está listo muestra el esqueleto del preview y se lanza solo al pasar a `ready`, también tras un `409 engine_not_ready`.
- El botón "Pegar" solo se renderiza en Chromium (`'userAgentData' in navigator` y `navigator.clipboard?.readText`).

Ver la spec, secciones "Estado del motor en el preview" y "Botón Pegar".

**Blocked by:** None (can start immediately).

**Status:** ready-for-agent

- [ ] Sin aviso rojo ni `role="alert"` con `null`, `missing` o `installing`; aviso neutro solo con `installing`.
- [ ] `error` se ve como hoy (mensaje y "Reintentar").
- [ ] Un enlace pegado durante `missing`/`installing` lanza el preview solo al pasar a `ready`, sin error.
- [ ] Un `409 engine_not_ready` del preview se espera y reintenta una vez al pasar a `ready`.
- [ ] El botón "Pegar" no aparece en Safari ni Firefox; aparece y funciona en Chrome.
- [ ] Tests de componente de cada estado, del preview diferido y de la detección del botón.

## Comments
