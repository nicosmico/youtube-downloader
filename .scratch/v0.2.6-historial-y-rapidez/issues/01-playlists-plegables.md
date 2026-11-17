# 01: Playlists plegables en el historial

**What to build:** En el listado (`frontend/src/app/downloads/downloads.{ts,html,spec.ts}`), cada playlist se puede plegar y desplegar.

**Blocked by:** None.

**Status:** ready-for-agent

## Diseño

- La cabecera de la playlist (título y resumen, p. ej. "8/8 completadas") es un botón que pliega o despliega, con una flecha (chevron) que gira, `aria-expanded` y `aria-controls`. El menú "⋮" de la cabecera sigue funcionando sin plegar ni desplegar (no propaga el clic).
- Plegada, solo se ve la cabecera; desplegada, las filas como hoy.
- Estado por defecto:
  - Desplegada si la playlist tiene algún job `queued` o en curso.
  - Plegada si todos sus jobs han terminado (cualquier estado final).
  - En el filtro "Con error", siempre desplegada (las filas tienen casillas para seleccionar).
  - El estado por defecto se recalcula al cambiar los jobs: una playlist que termina mientras la miras se pliega sola, salvo que el usuario la haya abierto o cerrado a mano.
- Si el usuario la abre o cierra a mano, se recuerda en `localStorage` por `batchId` (envuelto en `try/catch`; sin almacenamiento, funciona igual sin recordar). Limitar lo guardado (p. ej. las últimas 200 playlists) para que no crezca sin fin.
- Iconos: si `ui/icon.ts` no tiene un chevron, añádelo con el mismo estilo.

## Acceptance criteria

- [ ] Plegar y desplegar con clic y teclado (Enter/Espacio), con `aria-expanded`.
- [ ] Estado por defecto según las reglas de arriba, incluido "Con error" desplegada.
- [ ] Una playlist que termina se pliega sola salvo elección manual; la elección manual se recuerda al recargar.
- [ ] El menú "⋮" no pliega ni despliega.
- [ ] Tests en `downloads.spec.ts`; `npm run test:ci` y `npm run build` pasan.
- [ ] Sin textos que expliquen la UI.

## Comments
