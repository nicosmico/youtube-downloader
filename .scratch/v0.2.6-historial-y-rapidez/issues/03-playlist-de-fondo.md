# 03: "Ver playlist completa" al instante y "Descargar playlist" sin esperar

**What to build:** En `frontend/src/app/preview/url-preview.{ts,html,spec.ts}`. Hoy, el preview de un vídeo que trae `playlistUrl` carga la playlist en segundo plano (`playlistLoad`) para ofrecer "Descargar N". Dos cambios.

**Blocked by:** None.

**Status:** resolved

## 1. "Ver playlist completa" reutiliza la carga

- Si la playlist ya está cargada (`playlistLoad` en `ready`), "Ver playlist completa" muestra esa playlist al instante, sin volver a pedirla: cambia la URL del campo a `playlistUrl` y aplica el resultado como si hubiera llegado del servidor (selección de todos los disponibles incluida). Cuidado con que el cambio de URL no lance otra petición (el flujo de `requests` con `switchMap`).
- Si todavía está cargando, se espera a esa misma carga (no se lanza otra) mostrando el estado de carga habitual del preview.
- Si falló, se comporta como hoy (pide la playlist y muestra el error que toque).

## 2. "Descargar playlist" se puede pulsar mientras carga

- Mientras la playlist carga, el botón dice "Descargar playlist" y está **activo** (con el spinner pequeño que ya tiene).
- Si se pulsa durante la carga: el botón pasa a "Encolando…" (y el de "Descargar 1" se desactiva); cuando llega la playlist, se ponen en cola todas sus entradas disponibles con el formato que estaba elegido **al pulsar**, y después se limpia el campo como en cualquier descarga.
- Si la carga falla después de pulsar: no se pone nada en cola, el botón vuelve a su estado y se muestra el error en `enqueueError` (texto en `core/texts.ts`, p. ej. "No se pudo leer la playlist. Inténtalo de nuevo.").
- Si el usuario cambia o borra la URL antes de que llegue, se cancela todo y no se pone nada en cola.
- Si la playlist resulta tener 1 vídeo o ninguno disponible: se pone en cola lo que haya (1) o se muestra el error (0).

## Acceptance criteria

- [x] "Ver playlist completa" no hace una segunda petición si la playlist está cargada o cargando. Tests con fakes HTTP (contando peticiones).
- [x] "Descargar playlist" pulsable durante la carga; encola al llegar con el formato elegido al pulsar; limpia el campo. Tests.
- [x] Fallo tras pulsar: error visible, nada en cola. Cambiar la URL antes de llegar: nada en cola. Tests.
- [x] `npm run test:ci` y `npm run build` pasan.
- [x] Sin textos que expliquen la UI.

## Comments

**2026-11-17 — Resuelto.** Publicado en `v0.2.6` (release run `44138736518`; en main, CI `44138288876` y Native `44138288404`). Probado en Docker: "Descargar playlist" pulsado durante la carga encoló las 8 entradas al llegar y vació el campo. Antes de publicar se arregló un bug: "Ver playlist completa" anulaba sin aviso una descarga pendiente; ahora se desactiva mientras se encola.
