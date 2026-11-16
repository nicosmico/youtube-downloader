# Spec: v0.1.1 — hallazgos de la v0.1.0

**Status:** ready-for-agent

## Problem Statement

Las pruebas manuales de la v0.1.0 en un Mac real (2026-11-15) dejaron cuatro problemas: en macOS no se puede volver a abrir la app mientras ya está abierta; una descarga parece colgada en "Descargando 0 %" mientras `yt-dlp` prepara el video; la gestión de presets añade complejidad que no se usa; y cuando algo falla no hay forma de ver qué pasó sin abrir la terminal.

## Solution

Una versión de mantenimiento con cuatro cambios acotados: el `.app` de macOS pasa a ser un lanzador que arranca el servidor aparte; la tarjeta muestra "Preparando…" hasta que hay progreso real; los presets se reducen a dos atajos fijos; y la UI gana una sección "Registros" y el detalle de `yt-dlp` en cada job fallido.

## User Stories

1. Como usuario de macOS, quiero volver a abrir la app con doble clic aunque ya esté abierta, para recuperar la pestaña que cerré.
2. Como usuario, quiero ver "Preparando…" mientras la descarga todavía no empezó a recibir datos, para no pensar que está colgada.
3. Como usuario, quiero dos atajos, "Mejor video" y "MP3", para elegir lo habitual con un clic sin gestionar nada.
4. Como usuario, quiero ver los registros de la app en el navegador, para entender qué pasó cuando algo falla.
5. Como usuario, quiero copiar o descargar esos registros, para mandárselos a quien me ayude.
6. Como usuario, quiero ver el detalle de `yt-dlp` de una descarga fallida, para saber por qué falló.

## Implementation Decisions

### macOS: lanzador en segundo plano

- LaunchServices permite una sola instancia por bundle y, al reabrir, pide al proceso existente que se active. El servidor Python no es una app Cocoa y no responde, así que Finder muestra "La aplicación YouTube Downloader ya no está abierta." y la lógica de `Single Instance` nunca se ejecuta.
- Solución: en macOS empaquetado, el ejecutable del `.app` lanza el servidor como proceso hijo desacoplado (sesión nueva, fuera de LaunchServices) y termina enseguida. Cada doble clic arranca un lanzador nuevo que pasa por `Single Instance`.
- Consecuencia: no hay icono en el Dock mientras la app corre. Se cierra con "Cerrar aplicación" o por `Idle Shutdown`.
- Descartado: app Cocoa con PyObjC (icono en el Dock, "Salir" desde el Dock), por coste y riesgo.
- Desarrollo, Docker y Windows no cambian.

### "Preparando…"

- Un job `downloading` sin bytes descargados todavía se muestra como "Preparando…", sin barra de progreso. En cuanto llega la primera línea de progreso pasa a "Descargando" con porcentaje.
- Solo cambia la UI; el `Job Status` del backend no cambia.

### Presets fijos

- Solo existen "Mejor video" (video, `best`) y "MP3" (audio, `mp3`), como atajos de un clic junto a los selectores de modo, calidad y formato, que siguen visibles.
- Desaparecen "Guardar como preset", "Gestionar", renombrar y borrar.
- Se elimina la API `/api/presets` y la tabla `presets` (migración nueva que la borra). Los dos atajos son constantes del frontend.
- Las historias 11 a 13 del MVP quedan descartadas. El glosario redefine `Preset` como atajo fijo.

### Registros

- Sección "Registros" al final de la página, plegada por defecto. Se carga al abrirla con las últimas 500 líneas y tiene un botón "Actualizar"; no se actualiza en vivo.
- Fuentes:
  - Log del servidor (`$DATA_DIR/app.log`), sin las líneas de `uvicorn.access` salvo que se active el filtro "Mostrar peticiones".
  - Errores del frontend: errores de JavaScript no capturados y peticiones HTTP fallidas, en un buffer en memoria de la pestaña (no se persisten).
- Botones "Copiar" y "Descargar .txt" que incluyen ambas fuentes, con versión de la app, plataforma y versiones del Engine al principio.
- Cada job `failed` tiene un enlace "Ver detalle" con las últimas líneas de salida de `yt-dlp` (stdout y stderr) de su último `Attempt`.

## Testing Decisions

- Mismos criterios que el MVP: comportamiento externo, deterministas, sin red, sin asertos sobre el orden de arranque de jobs paralelos.
- El lanzador de macOS se valida en CI (`macos-latest`) arrancando el `.app` por el mismo camino que un doble clic (`open`) y a mano en un Mac real desde el zip del Release.

## Out of Scope

- Mostrar la posición de un job en la cola.
- Más de 2 descargas simultáneas.
- Reintento automático ante un `403` puntual de YouTube.
- Registros en vivo, filtrado por nivel o búsqueda dentro de los registros.
- Icono en el Dock o en la bandeja.

## Further Notes

- Se publica como `v0.1.1` con un tag, como la v0.1.0.
- Windows sigue sin verificación manual en un PC real; si aparece un hallazgo allí, se añade como ticket a este lote.
