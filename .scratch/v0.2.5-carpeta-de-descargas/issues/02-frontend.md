# 02: Frontend — carpeta de descargas en el menú del engranaje

**What to build:** La UI de la spec `../spec.md` (léela entera; la sección "API" es el contrato con el backend, que se hace en paralelo: usa fakes HTTP en los tests).

**Blocked by:** None.

**Status:** ready-for-agent

## Diseño

- `core/system.service.ts` (o un servicio nuevo pequeño): señal con el estado de la carpeta (`{path, display, isDefault, available}`), cargada con `GET /api/settings/download-dir` al iniciar y actualizada con el evento SSE `settings.updated` (mira cómo se manejan los otros eventos SSE, p. ej. `app.update`). Métodos `chooseDownloadDir()` (POST choose) y `resetDownloadDir()` (DELETE).
- `topbar/top-bar.html`, menú del engranaje: una sección "Carpeta de descargas" con:
  - la ruta `display` (truncada con elipsis si es larga, con la ruta completa en `title`);
  - si `available` es `false`, la ruta en el color de error y un texto corto "No disponible";
  - botón "Cambiar…": llama a choose; mientras el diálogo nativo está abierto, el botón se desactiva y muestra un spinner. Si responde `canceled`, no pasa nada. Si responde 501, 409 o 422, muestra el `message` del error en la sección, con el mecanismo de errores que ya use el menú (o un `<p role="alert">` pequeño).
  - botón "Restablecer", solo si `isDefault` es `false`.
- Si existe "Abrir carpeta de descargas" en el menú, se queda igual (ahora abre la configurada) y su error 409 se muestra como los demás.
- `frontend/src/app/preview/url-preview`: el error 409 `download_dir_unavailable` al poner en cola ya se muestra con `enqueueError` (comprueba que el `message` del servidor llega tal cual; si los errores de encolado se traducen por código, añade este código).
- Textos en `core/texts.ts`, en un bloque localizado.

## Acceptance criteria

- [ ] Sección en el menú con ruta, "Cambiar…" y "Restablecer" según el estado, con tests (Vitest + jsdom, fakes HTTP): carga inicial, elegir, cancelar, error 501, restablecer, actualización por SSE, no disponible.
- [ ] El error 409 al encolar se ve en el preview. Test.
- [ ] `npm run test:ci` y `npm run build` en `frontend/`.
- [ ] Sin textos que expliquen la UI.

## Comments
