# Spec: v0.2.0 — rediseño de la interfaz

**Status:** ready-for-agent

## Problem Statement

La UI de la v0.1.1 funciona, pero es una sola columna larga donde todo tiene el mismo peso: el preview, los atajos, el modo, la calidad, las descargas, el motor, los registros y "Cerrar aplicación". Tras pulsar "Descargar" hay que hacer scroll para ver el progreso, los atajos compiten con los selectores de formato, y la tarjeta del motor ocupa mucho para algo que casi nunca se mira. Además quedan dos fallos del lote anterior: la tarjeta muestra "En cola" cuando la descarga ya empezó, y la base de datos del entorno de desarrollo se corrompe.

## Solution

Un rediseño completo del frontend con Tailwind, inspirado en el estilo de YouTube (sin su marca ni su logo), con tema claro y oscuro, y un flujo que se entiende sin textos de ayuda: pegar el enlace, ver el preview, elegir formato y descargar, con las descargas siempre a la vista. Se corrigen los dos fallos pendientes.

## User Stories

1. Como usuario, quiero que el primer elemento que veo sea dónde pegar el enlace, para empezar sin pensar.
2. Como usuario, quiero un botón "Pegar" junto al campo, para no tener que usar el teclado.
3. Como usuario, quiero elegir el formato en un solo control, con "Mejor video" y "MP3" a un clic y el resto en "Otro formato", para no tener que entender modo, calidad y formato por separado.
4. Como usuario, quiero ver mis descargas en curso siempre a la vista, para saber al instante que la descarga empezó y cómo va.
5. Como usuario, quiero miniaturas en la lista de descargas, para reconocer cada una de un vistazo.
6. Como usuario, quiero separar lo que está en curso del historial, para no mezclar lo pendiente con lo terminado.
7. Como usuario, quiero que el estado del motor sea un indicador discreto que solo llame la atención si algo va mal.
8. Como usuario, quiero elegir tema claro, oscuro o el del sistema, y que la app lo recuerde.
9. Como usuario, quiero que las acciones poco frecuentes (registros, cerrar la app, quitar del historial) no estorben en el uso normal.
10. Como usuario, quiero que una descarga recién encolada muestre su estado real desde el primer momento, no "En cola" cuando ya empezó.

## Implementation Decisions

### Principios de UX

- La interfaz no se explica a sí misma con texto: sin pasos numerados ni notas de ayuda visibles. El orden lo dan la posición y la jerarquía visual.
- Se mantienen solo: placeholders, etiquetas accesibles (`aria-label`), tooltips en botones de icono, estados vacíos de una línea y mensajes de error accionables.
- Una sola acción primaria por vista: "Descargar" (rojo). El resto, secundarias o de icono.
- Tras una acción, feedback inmediato en el mismo lugar donde se mira (la fila nueva aparece arriba de "En curso"), no en otra parte de la página.
- Accesible por teclado: foco visible, orden lógico, `Esc` cierra menús y paneles, contraste AA en ambos temas.

### Estructura

- **Barra superior**: nombre de la app con un icono propio (flecha de descarga) a la izquierda; a la derecha, el indicador del motor, el botón de tema y el menú de engranaje. **Sin campo de texto en la barra**, para que no parezca un buscador.
- **Columna izquierda (flujo principal)**:
  - Campo de enlace con icono de enlace (no lupa), placeholder "Pega un enlace de YouTube" y botón "Pegar" (lee el portapapeles; si el navegador lo impide, enfoca el campo).
  - Con el campo vacío: estado vacío de una línea que nombra lo que acepta (videos, Shorts, playlists y canales).
  - Preview compacto: miniatura con duración, título, autor y resolución máxima. Para playlists, la lista de entradas con casillas debajo y el botón pasa a "Descargar N videos".
  - Control de formato: chips "Mejor video" y "MP3" y un tercer chip "Otro formato" que despliega todas las opciones agrupadas (Video: mejor, 2160p con aviso de VLC, 1080p, 720p, 480p; Audio: MP3, M4A, Opus). Sustituye al selector Video/Audio, a los desplegables y a los atajos de la v0.1.1. Las opciones no disponibles para el video se ven deshabilitadas.
  - Botón "Descargar".
- **Columna derecha (descargas)**: pestañas "En curso · N" e "Historial". Filas densas con miniatura, título, una línea de estado ("Audio · MP3 · 45 % · quedan 0:12", "Preparando…", "En cola", "Fallida" en rojo) y barra fina de progreso en rojo. Acciones frecuentes como icono con tooltip (cancelar, reintentar, mostrar archivo); el resto en un menú "⋮" (abrir carpeta, ver detalle, quitar del historial). Los lotes de playlist se agrupan bajo su título con el resumen "3/10 completadas".
- **Indicador del motor**: chip con punto verde ("Motor listo"), ámbar ("Instalando…", "Actualización pendiente") o rojo ("Motor con error"). Al pulsarlo, popover con versiones, "Actualizar yt-dlp" y, en error, "Reintentar". Solo cuando el motor no está listo aparece además un aviso destacado en la columna izquierda, porque bloquea las descargas.
- **Menú de engranaje**: tema (Sistema, Claro, Oscuro), "Registros" (abre un panel lateral con el contenido actual de la sección) y "Cerrar aplicación".
- **Ventanas estrechas** (< 900 px): una sola columna, con el flujo principal arriba y las descargas debajo.
- Pantallas de cierre ("La aplicación se cerró", por inactividad) con el mismo estilo.

### Estilo

- Tailwind CSS (versión estable vigente) integrado en el build de Angular; sin librerías de componentes.
- Tokens de color como variables CSS con dos juegos:
  - Claro: fondo `#ffffff`, superficie `#f2f2f2`, borde `#e5e5e5`, texto `#0f0f0f`, texto secundario `#606060`, acento `#e62117`.
  - Oscuro: fondo `#0f0f0f`, superficie `#212121`/`#272727`, borde `#303030`, texto `#f1f1f1`, texto secundario `#aaaaaa`, acento `#ff4e45`.
- Esquinas redondeadas (chips y botones en píldora, tarjetas de 12 px), sin sombras salvo en menús y popovers.
- Tipografía del sistema (`Roboto, -apple-system, "Segoe UI", Arial, sans-serif`); sin fuentes externas, porque la app es local.
- Iconos SVG en línea (un set de iconos de licencia libre empaquetado con la app, sin CDN).
- Tema: `system` por defecto (sigue `prefers-color-scheme`), con preferencia guardada en `localStorage`; se aplica antes del primer pintado para evitar el parpadeo.

### Miniaturas en las descargas

- Los jobs guardan `thumbnail` (URL de la miniatura del `MediaPreview` o de la `Entry`), con una migración nueva. Si falta, la fila muestra un marcador neutro.
- La miniatura la carga el navegador directamente desde YouTube, como en el preview.

### Fallo "En cola" (del lote anterior)

- La respuesta de `POST /api/jobs` y de `POST /api/jobs/{id}/retry` trae una foto del job anterior a su despacho, y a veces llega después del `job.updated` por SSE que ya dice `downloading`. La UI la aplica encima y la tarjeta vuelve a "En cola" hasta el primer progreso.
- Solución: los eventos SSE mandan. La respuesta HTTP solo añade el job si la UI todavía no lo conoce, y nunca sobrescribe un estado más reciente.

### Base de datos de desarrollo (del lote anterior)

- `.dev-data/db.sqlite3` apareció con la cabecera a ceros tras varias sesiones de Docker en OrbStack, probablemente por SQLite en modo WAL sobre una carpeta compartida con el host.
- Solución: en Compose, el directorio de datos pasa a un volumen de Docker (no a una carpeta del host); los binarios del Engine pueden seguir en una carpeta del host vía `ENGINE_BIN_DIR` para no descargarlos en cada volumen nuevo. Solo afecta al desarrollo; el producto no cambia.

## Testing Decisions

- Mismos criterios que el MVP: comportamiento externo, deterministas, sin red.
- Frontend: tests de componente para el flujo principal (estado vacío, pegar, preview de video y playlist, control de formato, descargar), la lista (pestañas, estados, acciones, menú "⋮", agrupación de lotes), el indicador del motor, el menú, el tema y el panel de registros. Test específico del orden de llegada respuesta HTTP / SSE.
- Revisión visual manual en el navegador, en ambos temas y en una ventana estrecha.

## Out of Scope

- Cambios de comportamiento del backend más allá de `thumbnail` y la corrección del orden de eventos.
- Búsqueda de videos dentro de la app.
- Arrastrar y soltar enlaces.
- Animaciones elaboradas.
- Internacionalización.

## Further Notes

- Se publica como `v0.2.0` con un tag, como las anteriores.
