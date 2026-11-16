# 03: Lista de descargas con miniaturas

**What to build:** La columna derecha: pestañas "En curso · N" e "Historial" (con "Cargar más"); filas densas con miniatura, título, línea de estado y barra fina de progreso; acciones frecuentes como iconos con tooltip y el resto en un menú "⋮"; agrupación de lotes de playlist con su resumen; "Ver detalle" de jobs fallidos dentro del menú o desplegado en la fila. Backend: los jobs guardan `thumbnail` (migración nueva), que la UI envía al encolar desde el `MediaPreview` o la `Entry`. Ver la spec, secciones "Estructura" y "Miniaturas en las descargas".

**Blocked by:** 01 (Base visual, tema y barra superior).

**Status:** ready-for-agent

- [x] `thumbnail` se guarda al encolar videos y entradas de playlist; una base de datos de la v0.1.1 migra sin errores; sin miniatura se ve un marcador neutro.
- [x] Una descarga recién encolada aparece arriba de "En curso" sin hacer scroll.
- [x] Todos los estados se ven correctamente: En cola, Preparando…, Descargando con datos, Procesando, Completada, Fallida, Cancelada, Interrumpida.
- [x] Cancelar, Reintentar, Mostrar archivo, Abrir carpeta, Ver detalle y Quitar del historial siguen funcionando.
- [x] Los lotes se agrupan con su resumen en ambas pestañas.
- [x] Tests de API (`thumbnail`) y de componente.

## Comments

2026-11-15: Backend: migración 6 (`jobs.thumbnail`), `thumbnail` en `POST /api/jobs` (video y `entries[]`; solo se guarda una URL https) y en el JSON de los jobs; las entradas del preview de playlist ahora traen `thumbnail` (`https://i.ytimg.com/vi/<id>/mqdefault.jpg`, porque `--flat-playlist` no la da). Una BD v0.1.1 migra sin errores (test) y se comprobó con la `.dev-data` real. Frontend: pestañas "En curso · N" / "Historial" (un job nuevo o reintentado vuelve a "En curso"), filas con miniatura de 72x40, una línea de estado, barra fina, iconos con tooltip (cancelar, reintentar, mostrar archivo) y menú "⋮" (abrir carpeta, ver detalle, quitar del historial). El resumen del lote cuenta todos sus jobs, no solo los de la pestaña. Verificado con tests de API y de componente, pytest, ruff y una descarga real (aparece como "Preparando…" desde el primer momento).
