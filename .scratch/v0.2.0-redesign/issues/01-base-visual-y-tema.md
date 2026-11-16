# 01: Base visual, tema y barra superior

**What to build:** Integrar Tailwind en el build de Angular con los tokens de color de la spec (claro y oscuro), la tipografía del sistema y un set de iconos SVG empaquetado. Tema `system`/`light`/`dark` guardado en `localStorage` y aplicado antes del primer pintado. Nueva estructura de página: barra superior (marca, indicador del motor con su popover, botón de tema y menú de engranaje con tema, "Registros" en panel lateral y "Cerrar aplicación"), y el esqueleto de dos columnas que pasa a una sola por debajo de 900 px. Las pantallas de cierre adoptan el nuevo estilo. Ver la spec, secciones "Estructura" y "Estilo".

**Blocked by:** None (can start immediately).

**Status:** resolved

- [x] Tailwind integrado; `npm run build` y la imagen de Docker siguen funcionando.
- [x] El tema sigue al sistema por defecto, se puede fijar en claro u oscuro, se recuerda y no parpadea al cargar.
- [x] La barra superior no contiene ningún campo de texto.
- [x] El indicador del motor muestra verde, ámbar o rojo y su popover ofrece versiones, "Actualizar yt-dlp" y "Reintentar" según el estado.
- [x] "Registros" se abre en un panel lateral y "Cerrar aplicación" funciona desde el menú.
- [x] Contraste AA y foco visible en ambos temas; `Esc` cierra menús y paneles.
- [x] Tests de componente del tema, el indicador, el menú y el panel.

## Comments

2026-11-15: Tailwind 4 (`tailwindcss` + `@tailwindcss/postcss`, vía `frontend/.postcssrc.json`, sin plugins de Angular). Tokens como variables CSS en `styles.css` (`:root` / `:root.dark`) expuestos con `@theme inline`; breakpoint `wide` = 900 px. Iconos: `lucide` (ISC) con imports con nombre, tree-shaken, renderizados por `<app-icon>`. Tema: `ThemeService` + script en línea de `index.html` (clase `dark` en `<html>`, `localStorage['theme']`). Verificado con tests de componente y de servicio (tema, chip, popover, menú, panel de Registros, pantallas de cierre), `npm run test:ci`, `npm run build`, `docker compose up --build` (la imagen compila con Tailwind) y una pasada manual en el navegador (tema oscuro, dos columnas). Desviación: los botones rellenos usan siempre `#e62117` (blanco sobre `#ff4e45` no llega a AA); el acento `#ff4e45` se usa en texto, barras y foco. Pendiente de la revisión visual: tema claro y ventana estrecha.

2026-11-16: Tras la revisión visual: esqueleto de carga del preview (con `motion-safe`), barra superior sin saltos de línea bajo 640 px (solo icono y punto del motor; nombre y etiqueta quedan para lectores de pantalla), foco azul neutro (`--focus`) en lugar de rojo, "Mostrar archivo" con icono de carpeta con lupa y "Preparando…" con el formato.

**2026-11-16 — Resuelto.** Publicado en `v0.2.0` (Native/Release `43878583896`, CI `43878578070`), tras la revisión visual del orquestador en claro, oscuro y 320 px.
