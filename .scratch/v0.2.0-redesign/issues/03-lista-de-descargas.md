# 03: Lista de descargas con miniaturas

**What to build:** La columna derecha: pestañas "En curso · N" e "Historial" (con "Cargar más"); filas densas con miniatura, título, línea de estado y barra fina de progreso; acciones frecuentes como iconos con tooltip y el resto en un menú "⋮"; agrupación de lotes de playlist con su resumen; "Ver detalle" de jobs fallidos dentro del menú o desplegado en la fila. Backend: los jobs guardan `thumbnail` (migración nueva), que la UI envía al encolar desde el `MediaPreview` o la `Entry`. Ver la spec, secciones "Estructura" y "Miniaturas en las descargas".

**Blocked by:** 01 (Base visual, tema y barra superior).

**Status:** ready-for-agent

- [ ] `thumbnail` se guarda al encolar videos y entradas de playlist; una base de datos de la v0.1.1 migra sin errores; sin miniatura se ve un marcador neutro.
- [ ] Una descarga recién encolada aparece arriba de "En curso" sin hacer scroll.
- [ ] Todos los estados se ven correctamente: En cola, Preparando…, Descargando con datos, Procesando, Completada, Fallida, Cancelada, Interrumpida.
- [ ] Cancelar, Reintentar, Mostrar archivo, Abrir carpeta, Ver detalle y Quitar del historial siguen funcionando.
- [ ] Los lotes se agrupan con su resumen en ambas pestañas.
- [ ] Tests de API (`thumbnail`) y de componente.
