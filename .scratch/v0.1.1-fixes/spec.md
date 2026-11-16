# Spec: v0.1.1 — lote de hallazgos de la v0.1.0

**Status:** needs-triage

Hallazgos de las pruebas manuales de la v0.1.0 (GitHub Release, 2026-11-15) en un Mac real y, si es posible, en Windows. Cada hallazgo es un ticket en `issues/`. Cuando el lote esté completo se triagea, se implementa y se publica la `v0.1.1`.

## Decisiones tomadas

- **macOS, reabrir la app:** el `.app` pasa a ser un lanzador que arranca el servidor como proceso aparte y termina (ticket 01). Sin icono en el Dock mientras la app corre; se cierra con "Cerrar aplicación" o por `Idle Shutdown`.
