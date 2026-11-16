# 02: Versión en el engranaje y aviso de versión nueva

**What to build:**

*Backend:* al arrancar, una comprobación en segundo plano y de una sola vez del último Release de la app:
- Pide `https://github.com/nicosmico/youtube-downloader/releases/latest` con `Fetcher.redirect_location` y parsea el tag `vX.Y.Z`.
- Si la versión publicada es mayor que `__version__`, expone `update: {version, url}` en `/api/health` (`null` si no hay) y publica el evento SSE `app.update` con ese mismo objeto.
- Si falla, lo registra en el log y no muestra nada.
- Se desactiva con `UPDATE_CHECK=0`.

*Frontend:*
- La línea `Versión X.Y.Z` al final del menú del engranaje.
- Si hay `update`, un chip-enlace en la barra superior junto al indicador del motor: flecha hacia arriba + `vX.Y.Z`, que abre `url` en una pestaña nueva. Bajo 640 px solo el icono. `aria-label`/`title`: "Hay una versión nueva: X.Y.Z".
- El chip se actualiza al recibir `app.update`.

Ver la spec, secciones "Versión en el engranaje" y "Aviso de versión nueva", y el ADR-0011.

**Blocked by:** None (can start immediately).

**Status:** ready-for-agent

- [ ] La comprobación no bloquea el arranque ni el Engine. Con la red caída, no muestra nada y no deja errores visibles.
- [ ] La comparación de versiones es numérica (`0.10.0` > `0.9.0`) y solo avisa si la publicada es estrictamente mayor.
- [ ] La `url` se construye a partir del tag parseado, nunca copiando la `Location`.
- [ ] `/api/health` incluye `update`, y el evento `app.update` llega a las pestañas abiertas.
- [ ] `UPDATE_CHECK=0` no hace ninguna petición. Los tests del backend no tocan la red.
- [ ] El menú del engranaje muestra la versión instalada.
- [ ] El chip aparece solo con `update`, con contraste AA y foco visible en ambos temas, y sin saltos de línea a 320 px.
- [ ] Tests de backend (versión, parseo, checker con `Fetcher` falso, health, evento, desactivado) y de frontend (chip, SSE, línea de versión).

## Comments
