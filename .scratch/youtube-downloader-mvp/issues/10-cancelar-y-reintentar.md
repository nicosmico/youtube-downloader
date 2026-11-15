# 10: Cancelar y reintentar

**What to build:** El usuario puede cancelar un job en cola o en curso. La cancelación termina el árbol de procesos sin dejar huérfanos, borra el staging del job y lo deja en `canceled`. Puede reintentar jobs `failed`, `canceled` o `interrupted`, creando un nuevo `Attempt` con staging limpio sin duplicar archivos. En Windows se termina el árbol completo de procesos (Job Object o equivalente).

**Blocked by:** 06 (Cola persistente y concurrencia).

**Status:** ready-for-agent

- [ ] Cancelar un job en cola lo saca sin ejecutarlo.
- [ ] Cancelar un job activo termina `yt-dlp` y sus hijos (`ffmpeg`, Deno), borra su staging y deja el estado `canceled`.
- [ ] No quedan procesos huérfanos tras cancelar.
- [ ] Reintentar un job fallido lo reencola con `attempt + 1` y puede completarse.
- [ ] Un job `interrupted` se puede reintentar.
- [ ] Al arrancar se limpian las carpetas de staging sin job activo.
- [ ] Tests con `FakeEngine` que simula cuelgue y fallo.
