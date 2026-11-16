# 02: Flujo principal (enlace, preview, formato)

**What to build:** La columna izquierda: campo de enlace con icono de enlace, placeholder "Pega un enlace de YouTube" y botón "Pegar"; estado vacío de una línea; preview compacto de video y de playlist (con la lista de entradas, casillas y "Descargar N videos"); control de formato único con los chips "Mejor video", "MP3" y "Otro formato" (todas las opciones agrupadas, las no disponibles deshabilitadas, aviso de VLC en 2160p); botón "Descargar"; aviso destacado solo cuando el motor no está listo. Sustituye al selector Video/Audio, los desplegables y los atajos actuales. Sin textos de ayuda visibles. Ver la spec, sección "Estructura".

**Blocked by:** 01 (Base visual, tema y barra superior).

**Status:** ready-for-agent

- [ ] Con el campo vacío se ve el estado vacío; "Pegar" lee el portapapeles o, si el navegador no lo permite, enfoca el campo.
- [ ] Preview de video y de playlist con el nuevo estilo, conservando los errores y la selección de entradas actuales.
- [ ] El control de formato cubre todas las combinaciones válidas de la v0.1.1 y aplica el fallback a `best`.
- [ ] La elección de formato se conserva al previsualizar otro enlace.
- [ ] Sin pasos numerados ni notas de ayuda visibles.
- [ ] Tests de componente del flujo completo.
