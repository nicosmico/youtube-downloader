# 02: Flujo principal (enlace, preview, formato)

**What to build:** La columna izquierda: campo de enlace con icono de enlace, placeholder "Pega un enlace de YouTube" y botón "Pegar"; estado vacío de una línea; preview compacto de video y de playlist (con la lista de entradas, casillas y "Descargar N videos"); control de formato único con los chips "Mejor video", "MP3" y "Otro formato" (todas las opciones agrupadas, las no disponibles deshabilitadas, aviso de VLC en 2160p); botón "Descargar"; aviso destacado solo cuando el motor no está listo. Sustituye al selector Video/Audio, los desplegables y los atajos actuales. Sin textos de ayuda visibles. Ver la spec, sección "Estructura".

**Blocked by:** 01 (Base visual, tema y barra superior).

**Status:** resolved

- [x] Con el campo vacío se ve el estado vacío; "Pegar" lee el portapapeles o, si el navegador no lo permite, enfoca el campo.
- [x] Preview de video y de playlist con el nuevo estilo, conservando los errores y la selección de entradas actuales.
- [x] El control de formato cubre todas las combinaciones válidas de la v0.1.1 y aplica el fallback a `best`.
- [x] La elección de formato se conserva al previsualizar otro enlace.
- [x] Sin pasos numerados ni notas de ayuda visibles.
- [x] Tests de componente del flujo completo.

## Comments

2026-11-15: Columna izquierda reescrita (`UrlPreview`): campo con icono de enlace y "Pegar" (Clipboard API; si falla o está vacío, enfoca el campo), botón de borrar, estado vacío de una línea, preview compacto con duración sobre la miniatura, chips "Mejor video" / "MP3" / "Otro formato ▾" (menú agrupado Video/Audio con 2160p marcado "puede requerir VLC" y opciones no disponibles deshabilitadas), "Descargar" y aviso destacado con "Reintentar" cuando el motor falla. Sin textos de ayuda; `presets.ts` se conserva como origen de los dos chips. La elección de formato se conserva entre previews y el fallback a `best` sigue igual. Verificado con 95 tests de componente y una descarga real en el navegador.

2026-11-16: Tras la revisión visual: esqueleto de carga del preview (con `motion-safe`), barra superior sin saltos de línea bajo 640 px (solo icono y punto del motor; nombre y etiqueta quedan para lectores de pantalla), foco azul neutro (`--focus`) en lugar de rojo, "Mostrar archivo" con icono de carpeta con lupa y "Preparando…" con el formato.

**2026-11-16 — Resuelto.** Publicado en `v0.2.0` (Native/Release `43878583896`, CI `43878578070`), tras la revisión visual del orquestador en claro, oscuro y 320 px.
