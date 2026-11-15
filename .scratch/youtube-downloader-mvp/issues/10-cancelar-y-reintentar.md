# 10: Cancelar y reintentar

**What to build:** El usuario puede cancelar un job en cola o en curso. La cancelación termina el grupo de procesos sin dejar huérfanos y deja el job en `canceled`. Puede reintentar jobs `failed`, `canceled` o `interrupted`, incrementando el intento sin duplicar archivos.

**Blocked by:** 06 (Cola persistente y concurrencia).

**Status:** ready-for-agent

- [ ] Cancelar un job en cola lo saca sin ejecutarlo.
- [ ] Cancelar un job activo termina `yt-dlp` y deja el estado `canceled`.
- [ ] No quedan procesos huérfanos tras cancelar.
- [ ] Reintentar un job fallido lo reencola y puede completarse.
- [ ] Un job `interrupted` se puede reintentar.
- [ ] Tests con `FakeEngine` que simula cuelgue y fallo.
