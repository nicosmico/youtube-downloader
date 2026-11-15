---
status: accepted
---

# FastAPI sirve la SPA de Angular y emite progreso por SSE

El backend es Python por el acceso directo a subprocess, filesystem y empaquetado con PyInstaller. El frontend es Angular compilado a estáticos que FastAPI sirve en `/`; el progreso viaja por Server-Sent Events en una sola dirección.

## Considered Options

- **WebSockets**: descartado; no se necesitan comandos por el canal, solo eventos del servidor.
- **Node/Electron**: descartado por peso y por duplicar runtime.
- **React**: descartado por preferencia explícita por Angular.

## Consequences

- Un solo origen y un solo proceso en producción; no hay CORS.
- El cliente debe reconectar SSE y rehidratar estado con `GET /api/jobs` al volver.
