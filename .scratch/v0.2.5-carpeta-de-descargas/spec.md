# Spec: v0.2.5 — carpeta de descargas configurable

**Status:** in-progress

## Problem Statement

Todo se descarga en `~/Downloads` (ADR-0007). El usuario quiere poder elegir otra carpeta, con Descargas como valor por defecto (2026-11-17).

## Solution

En el menú del engranaje, una línea "Carpeta de descargas" muestra la carpeta actual, con "Cambiar…" (abre el diálogo de carpetas del sistema) y "Restablecer" (solo si no es la de por defecto). Decisión en `docs/adr/0012-carpeta-de-descargas-configurable.md`.

## User Stories

1. Como usuario, quiero elegir en qué carpeta se guardan mis descargas, con el diálogo de mi sistema.
2. Como usuario, quiero volver a Descargas con un clic.
3. Como usuario, quiero que lo que ya está en cola no cambie de carpeta a mitad.
4. Como usuario con un disco externo, quiero un aviso claro si la carpeta elegida no está disponible, y no que se guarde en otro sitio sin avisar.
5. Como usuario, quiero que "Abrir carpeta" abra la carpeta elegida.

## API (contrato entre los tickets 01 y 02)

Todas con la cabecera `X-Requested-With: youtube-downloader`, como el resto de mutaciones.

- `GET /api/settings/download-dir` → `{"path": "/Users/ana/Música", "display": "~/Música", "isDefault": false, "available": true}`.
  - `display`: la ruta con el home abreviado a `~` (en Windows, la ruta completa).
  - `available`: la carpeta existe y es un directorio (la de por defecto cuenta como disponible: se crea al descargar).
- `POST /api/settings/download-dir/choose` → abre el diálogo nativo (bloquea hasta que el usuario elige o cancela; corre en un hilo, no en el event loop).
  - Elegida: guarda y devuelve el mismo objeto que el `GET`.
  - Cancelada: `{"canceled": true}` (200), sin cambios.
  - Sin diálogo nativo (Linux/Docker): 501 `picker_unavailable`, "Esta acción solo funciona en la aplicación de escritorio (macOS o Windows)."
  - Ya hay un diálogo abierto: 409 `picker_busy`.
  - Carpeta sin permiso de escritura: 422 `download_dir_not_writable`, "No se puede escribir en esa carpeta. Elige otra."
- `PUT /api/settings/download-dir` con `{"path": "..."}` → misma validación (ruta absoluta, existe, es directorio, se puede escribir; si no, 422 `invalid_download_dir` o `download_dir_not_writable`). Para pruebas y desarrollo; la UI no lo usa.
- `DELETE /api/settings/download-dir` → vuelve a la de por defecto; devuelve el objeto del `GET`.
- Evento SSE `settings.updated` con el objeto del `GET` cada vez que cambia, para que otras pestañas se actualicen.
- `POST /api/jobs`: si la carpeta configurada no es la de por defecto y no está disponible, 409 `download_dir_unavailable`, "La carpeta {display} no está disponible. Conecta el disco o elige otra carpeta."
- `POST /api/system/open-downloads`: abre la carpeta configurada.

## Implementation Decisions

- Detalle en `issues/01-backend.md` y `issues/02-frontend.md`. Se pueden hacer en paralelo con el contrato de arriba.
- Textos en español, sin explicar la UI.

## Testing Decisions

- Mismos criterios de siempre: deterministas, sin red, sin abrir diálogos reales (el selector se inyecta).
- Prueba manual en el Docker de desarrollo con `PUT`, y del diálogo real en un Mac.

## Out of Scope

- Una carpeta distinta por descarga o por formato.
- Mover descargas ya hechas al cambiar de carpeta.

## Further Notes

- Se publica como `v0.2.5`.
