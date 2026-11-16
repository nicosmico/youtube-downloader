# 01: Base visual, tema y barra superior

**What to build:** Integrar Tailwind en el build de Angular con los tokens de color de la spec (claro y oscuro), la tipografía del sistema y un set de iconos SVG empaquetado. Tema `system`/`light`/`dark` guardado en `localStorage` y aplicado antes del primer pintado. Nueva estructura de página: barra superior (marca, indicador del motor con su popover, botón de tema y menú de engranaje con tema, "Registros" en panel lateral y "Cerrar aplicación"), y el esqueleto de dos columnas que pasa a una sola por debajo de 900 px. Las pantallas de cierre adoptan el nuevo estilo. Ver la spec, secciones "Estructura" y "Estilo".

**Blocked by:** None (can start immediately).

**Status:** ready-for-agent

- [ ] Tailwind integrado; `npm run build` y la imagen de Docker siguen funcionando.
- [ ] El tema sigue al sistema por defecto, se puede fijar en claro u oscuro, se recuerda y no parpadea al cargar.
- [ ] La barra superior no contiene ningún campo de texto.
- [ ] El indicador del motor muestra verde, ámbar o rojo y su popover ofrece versiones, "Actualizar yt-dlp" y "Reintentar" según el estado.
- [ ] "Registros" se abre en un panel lateral y "Cerrar aplicación" funciona desde el menú.
- [ ] Contraste AA y foco visible en ambos temas; `Esc` cierra menús y paneles.
- [ ] Tests de componente del tema, el indicador, el menú y el panel.
