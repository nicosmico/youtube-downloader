# 04: Sección "Registros"

**What to build:** Una sección "Registros" al final de la página, plegada por defecto. Al abrirla carga las últimas 500 líneas del log del servidor (`$DATA_DIR/app.log`) sin las líneas de `uvicorn.access`, salvo que se active "Mostrar peticiones", más los errores del frontend (JavaScript no capturado y peticiones HTTP fallidas) que la pestaña guarda en memoria. Botón "Actualizar"; botones "Copiar" y "Descargar .txt" con ambas fuentes y una cabecera con versión de la app, plataforma y versiones del Engine. Ver la sección "Registros" de la spec.

**Blocked by:** None (can start immediately).

**Status:** ready-for-agent

- [ ] Un endpoint de solo lectura devuelve las últimas N líneas del log (máximo 500), con o sin peticiones, sin bloquear al runner.
- [ ] La sección está plegada por defecto y solo pide datos al abrirse o al pulsar "Actualizar".
- [ ] Los errores del frontend se capturan en un buffer acotado en memoria y aparecen en la sección.
- [ ] "Copiar" y "Descargar .txt" incluyen la cabecera y ambas fuentes.
- [ ] Funciona en el ejecutable sin consola de Windows, donde el log solo va a archivo.
- [ ] Tests de API y de componente.
