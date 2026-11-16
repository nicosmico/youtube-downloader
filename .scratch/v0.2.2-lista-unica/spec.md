# Spec: v0.2.2 — una sola lista de descargas y limpieza del historial

**Status:** resolved

## Problem Statement

Pruebas de la v0.2.1 en un Mac real (2026-11-16):

- Al abrir la app aparece un aviso rojo, "El motor de descarga no está listo.", durante los segundos en que el motor todavía se está comprobando. Es un estado normal, pero parece un error.
- En Safari, el botón "Pegar" abre una segunda burbuja "Pegar" del navegador, que confunde.
- Al terminar, una descarga sale de la pestaña "En curso" y pasa a "Historial". Para el usuario, la descarga "se fue".
- No se puede quitar una playlist entera del historial, ni vaciar el historial, sin ir entrada por entrada.

## Solution

- El estado transitorio del motor deja de mostrarse como error.
- El botón "Pegar" solo aparece donde funciona con un clic.
- Las pestañas "En curso" e "Historial" se sustituyen por una sola lista con filtros por estado y agrupada por día.
- Se puede quitar del historial una playlist completa o vaciarlo entero, con confirmación y sin tocar los archivos.

## User Stories

1. Como usuario, quiero que la app no me muestre un error mientras arranca con normalidad, para no pensar que algo está roto.
2. Como usuario, quiero poder pegar un enlace mientras el motor termina de prepararse, y que el preview salga solo cuando esté listo.
3. Como usuario de Safari o Firefox, no quiero un botón "Pegar" que abre otro "Pegar"; me basta con ⌘V.
4. Como usuario, quiero que una descarga se quede en el mismo sitio de la lista al terminar y solo cambie su estado.
5. Como usuario, quiero filtrar la lista: todas, en curso, completadas, con error o canceladas.
6. Como usuario, quiero la lista agrupada por día, para ubicar lo que bajé hoy, ayer o hace una semana.
7. Como usuario, quiero quitar una playlist completa del historial de una vez.
8. Como usuario, quiero vaciar el historial de una vez.
9. Como usuario, quiero una confirmación antes de quitar muchas entradas, y saber que mis archivos no se borran.

## Implementation Decisions

### Estado del motor en el preview (frontend)

- `EngineStatus` del backend: `missing`, `installing`, `ready` y `error`. Mientras no se conoce (`null`), o es `missing` o `installing`, el estado es transitorio:
  - No se muestra ningún aviso rojo ni `role="alert"`.
  - Mientras es `null` o `missing` y dura poco (comprobación al arrancar), no se muestra nada.
  - Si es `installing` (primera instalación o reparación), se muestra un aviso neutro con un indicador de actividad, en el estilo de superficie neutra de la app y sin icono de alerta: "Preparando el motor…".
  - El campo del enlace sigue disponible. Si el usuario pega o escribe un enlace, el preview muestra su estado de carga normal (el esqueleto) y se lanza solo en cuanto el motor pasa a `ready`.
  - Si la petición de preview recibe `409 engine_not_ready` (carrera con el estado), se trata igual: se espera a `ready` y se reintenta una vez, sin mostrar error.
- `error`: el aviso rojo de hoy, con el mensaje y "Reintentar", sin cambios.
- La sección "Descargar" (chips de formato y botón) sigue la misma regla: deshabilitada mientras el motor no está listo, sin mensaje de error.

### Botón "Pegar" (frontend)

- Solo se muestra donde `navigator.clipboard.readText` lee directamente tras el primer permiso: navegadores Chromium (Chrome, Edge). Se detecta por capacidad, con `'userAgentData' in navigator` (solo existe en Chromium) y `navigator.clipboard?.readText`, no por el texto del user agent.
- En Safari y Firefox el botón no se renderiza. El campo acepta ⌘V/Ctrl+V y el pegado ya lanza el preview al instante.

### Una sola lista de descargas (frontend)

- Desaparecen las pestañas "En curso" e "Historial". Hay una sola lista: la más reciente arriba, por `createdAt` descendente (el mismo orden que la API). Un job no cambia de posición al cambiar de estado.
- Filtros como chips encima de la lista, en una fila con scroll horizontal si no cabe:

| Chip | Estados |
|---|---|
| Todas (por defecto) | todos |
| En curso · N | `queued`, `downloading`, `processing` (N = `active + queued` de `queue.updated`) |
| Completadas | `completed` |
| Con error | `failed`, `interrupted` |
| Canceladas | `canceled` |

- El filtro no puede dejar la lista vacía solo porque los jobs que coinciden están en una página aún no cargada. Con un filtro de estados terminales, la consulta a `/api/jobs` usa `status=` con esos estados y su propio cursor de "Cargar más". "Todas" combina los jobs en curso (todos) con las páginas del historial, ordenados por `createdAt`.
- Al encolar una descarga con un filtro que no la muestra (por ejemplo "Completadas"), el filtro vuelve a "Todas" para que se vea al instante.
- Agrupación por día local del navegador según `createdAt`. Cabeceras simples, no plegables: "Hoy", "Ayer" y después la fecha corta en español ("12 nov", con el año solo si no es el actual). Una playlist (Batch) se muestra como una sola tarjeta en el día de su job más reciente.
- Estado vacío por filtro, con una frase corta y sin texto de ayuda: "No hay descargas.", "No hay descargas en curso.", etc.
- La tarjeta del job y la del Batch mantienen su diseño actual (miniatura, estado, progreso, acciones).

### Quitar una playlist y vaciar el historial

**Backend**
- `DELETE /api/batches/{batch_id}`: quita del historial todos los jobs terminales (`completed`, `failed`, `canceled`, `interrupted`) de ese Batch, en una sola sentencia atómica (`DELETE … WHERE batch_id = ? AND status IN (…) RETURNING id`), para no quitar un job que un reintento acaba de volver a encolar. Los jobs en curso se quedan. El Batch se borra cuando ya no le quedan jobs. Responde `200 {"removed": n}` (n puede ser 0). Si el Batch no existe, `404 batch_not_found`.
- `DELETE /api/history`: quita todos los jobs terminales, con la misma regla atómica, y los Batches que quedan vacíos. Responde `200 {"removed": n}`.
- Ninguno toca archivos en disco. `job_output` se borra en cascada (`ON DELETE CASCADE`).
- Si `n > 0`, se publica un único evento SSE nuevo, `jobs.removed`, con `{"ids": [...]}`. El `job.removed` de un solo job no cambia.
- Ambos pasan por el middleware de seguridad local, como el resto de la API.

**Frontend**
- En la tarjeta de un Batch, un menú `⋮` con "Quitar del historial". Solo está activo si el Batch tiene algún job terminal.
- Encima de la lista, en la fila de filtros, un menú `⋮` con "Vaciar historial".
- Ambas acciones piden confirmación con un diálogo modal accesible (`<dialog>` nativo, foco atrapado, `Esc` cancela, el foco vuelve al botón de origen):
  - Playlist: título "¿Quitar N descargas del historial?", texto "Los archivos descargados no se borran.", botones "Cancelar" y "Quitar". N es el número de jobs terminales del Batch que conoce el cliente.
  - Historial: título "¿Vaciar el historial?", texto "Se quitan todas las descargas terminadas. Los archivos descargados no se borran.", botones "Cancelar" y "Vaciar".
- `JobsService` escucha `jobs.removed` y quita esos ids (todas las pestañas abiertas se actualizan). Tras la respuesta HTTP se quitan también localmente.

## Testing Decisions

- Mismos criterios de siempre: comportamiento externo, deterministas y sin red. Los specs no importan otros specs; los datos compartidos van en `frontend/src/testing/fixtures.ts`.
- Backend:
  - `DELETE /api/batches/{id}` quita solo los terminales, deja los que están en curso y borra el Batch cuando queda vacío.
  - 404 si el Batch no existe.
  - `DELETE /api/history` quita solo los terminales.
  - Se publica `jobs.removed` con los ids, y no se publica nada si `n = 0`.
  - `job_output` se borra con su job.
  - No se toca ningún archivo.
- Frontend:
  - Estados del motor en el preview: nada con `null`/`missing`, neutro con `installing`, rojo con `error`, y preview diferido que se lanza al pasar a `ready`.
  - El botón "Pegar" aparece o no según la capacidad.
  - Filtros y sus consultas.
  - Agrupación por día (Hoy, Ayer, fecha), con un reloj inyectable o fechas fijas.
  - Un job que pasa a `completed` no cambia de posición.
  - Diálogos de confirmación: confirmar, cancelar, `Esc` y foco.
  - `jobs.removed`.

## Out of Scope

- Borrar archivos del disco.
- Deshacer después de quitar.
- Búsqueda de texto en la lista.
- Miniaturas de las entradas de playlists que no las tienen.
- Acordeón por día.

## Further Notes

- Se publica como `v0.2.2`. Es la primera versión en la que una v0.2.1 instalada mostrará el chip de versión nueva.
