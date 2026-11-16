# 04: Sección "Registros"

**What to build:** Una sección "Registros" al final de la página, plegada por defecto. Al abrirla carga las últimas 500 líneas del log del servidor (`$DATA_DIR/app.log`) sin las líneas de `uvicorn.access`, salvo que se active "Mostrar peticiones", más los errores del frontend (JavaScript no capturado y peticiones HTTP fallidas) que la pestaña guarda en memoria. Botón "Actualizar"; botones "Copiar" y "Descargar .txt" con ambas fuentes y una cabecera con versión de la app, plataforma y versiones del Engine. Ver la sección "Registros" de la spec.

**Blocked by:** None (can start immediately).

**Status:** ready-for-agent

- [x] Un endpoint de solo lectura devuelve las últimas N líneas del log (máximo 500), con o sin peticiones, sin bloquear al runner.
- [x] La sección está plegada por defecto y solo pide datos al abrirse o al pulsar "Actualizar".
- [x] Los errores del frontend se capturan en un buffer acotado en memoria y aparecen en la sección.
- [x] "Copiar" y "Descargar .txt" incluyen la cabecera y ambas fuentes.
- [x] Funciona en el ejecutable sin consola de Windows, donde el log solo va a archivo.
- [x] Tests de API y de componente.

## Comments

**2026-11-15**: implementado en la rama `ticket/v011-app` (sin push).

- `GET /api/logs?lines=500&requests=false` (`app/logs.py`): lee `app.log` hacia atrás por bloques de 64 KB y sigue en `app.log.1` si hace falta; filtra `uvicorn.access` antes de contar. `def` sin `async`: corre en el pool de hilos, fuera del event loop. `lines` de 1 a 500 (422 fuera de rango).
- Frontend: `ErrorLogService` (buffer de 100 entradas en memoria), `AppErrorHandler` (errores JS no capturados; `provideBrowserGlobalErrorListeners` ya le reenvía `error` y `unhandledrejection`) e interceptor de peticiones HTTP fallidas (método, URL y estado, sin cuerpos). Componente `Logs` al final de la página, plegado; pide datos solo al abrir, con "Actualizar" y al cambiar "Mostrar peticiones". "Copiar" y "Descargar .txt" usan el mismo informe con cabecera (app, plataforma, Engine).
- Sin consola (Windows): test que configura el logging con `sys.stderr = None` y comprueba que el endpoint lee lo escrito.
- Verificado con tests y en la app real: el log omite `uvicorn.access`, un error JS provocado aparece en la sección y el texto copiado trae cabecera, servidor y frontend.
