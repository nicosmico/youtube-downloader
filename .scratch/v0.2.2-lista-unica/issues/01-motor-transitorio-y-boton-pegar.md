# 01: Estado transitorio del motor y botón "Pegar"

**What to build:** En el preview (`frontend/src/app/preview/`):
- El motor en estado `null`, `missing` o `installing` deja de mostrarse como error. Con `null` o `missing` no se muestra nada; con `installing`, un aviso neutro "Preparando el motor…" con indicador de actividad.
- El rojo queda solo para `error`.
- Un enlace pegado mientras el motor no está listo muestra el esqueleto del preview y se lanza solo al pasar a `ready`, también tras un `409 engine_not_ready`.
- El botón "Pegar" solo se renderiza en Chromium (`'userAgentData' in navigator` y `navigator.clipboard?.readText`).

Ver la spec, secciones "Estado del motor en el preview" y "Botón Pegar".

**Blocked by:** None (can start immediately).

**Status:** resolved

- [x] Sin aviso rojo ni `role="alert"` con `null`, `missing` o `installing`; aviso neutro solo con `installing`.
- [x] `error` se ve como hoy (mensaje y "Reintentar").
- [x] Un enlace pegado durante `missing`/`installing` lanza el preview solo al pasar a `ready`, sin error.
- [x] Un `409 engine_not_ready` del preview se espera y reintenta una vez al pasar a `ready`.
- [x] El botón "Pegar" no aparece en Safari ni Firefox; aparece y funciona en Chrome.
- [x] Tests de componente de cada estado, del preview diferido y de la detección del botón.

## Comments

### 2026-11-16 (agente)

Hecho en `frontend/src/app/preview/` y `core/texts.ts` (solo `preview.enginePreparing`).

- Aviso del motor: `null`/`missing` no renderizan nada; `installing` muestra un aviso neutro (`bg-surface`, `border-line`, texto `muted`, spinner CSS con `motion-safe`, `role="status"`, sin icono); `error` mantiene el aviso rojo con mensaje y "Reintentar". El campo de enlace y el botón Pegar ya no se deshabilitan por el motor.
- Preview diferido: el `switchMap` de peticiones espera a `engineReady` (`toObservable` + `defer`) antes de llamar a `PreviewService`, con `startWith(loading)`, por lo que sale el esqueleto y se conservan el debounce y la cancelación de peticiones obsoletas. Un `409 engine_not_ready` espera a `ready` y reintenta una vez; si el reintento vuelve a dar 409 se muestra el error normal.
- Pegar: `detectPasteSupport()` (`'userAgentData' in navigator && typeof navigator.clipboard?.readText === 'function'`) tras el token inyectable `PASTE_SUPPORT` (valor: función, evaluada por componente).
- Desviaciones: (1) el efecto que vaciaba la pantalla al perder el motor ahora respeta un estado `loading` pendiente, para no perder el esqueleto; (2) el texto de estado vacío ("Videos, Shorts, ...") ahora se muestra también con el motor no listo, para evitar un salto de layout al arrancar; (3) el reintento tras 409 con el motor ya `ready` en el cliente es inmediato (no hay llamada extra a `refresh()`).
- Verificado: `npm run test:ci` (265 tests, 10 archivos) y `npm run build` pasan. Tests nuevos de componente: estados `null`/`missing`/`installing`/`error`, preview diferido (pegado y tecleado, último enlace gana, borrar cancela), 409 con reintento y con doble 409, botón Pegar por capacidad y `detectPasteSupport`. Sin comprobar a mano en un navegador real.

**2026-11-16 — Resuelto.** Publicado en `v0.2.2` (Native/Release `43963527519`; en main, CI `43963250355` y Native `43963250353`). Revisión del orquestador contra el backend real: playlist de prueba, filtros, quitar playlist, vaciar historial (archivos intactos), arranque sin aviso rojo, claro, oscuro y 320 px. Corrección añadida en la integración: la confirmación de cancelar desaparece si la descarga termina mientras tanto.
