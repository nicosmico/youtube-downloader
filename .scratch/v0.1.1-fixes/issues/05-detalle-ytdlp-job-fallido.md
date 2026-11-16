# 05: "Ver detalle" en jobs fallidos

**What to build:** Cada job `failed` muestra un enlace "Ver detalle" que despliega las últimas líneas de salida de `yt-dlp` (stdout y stderr) de su último `Attempt`, para entender por qué falló más allá del mensaje saneado. La salida se guarda acotada por `Attempt` y se descarta con un reintento o al quitar el job del historial. Ver la sección "Registros" de la spec.

**Blocked by:** None (can start immediately).

**Status:** ready-for-agent

- [ ] El runner guarda las últimas líneas de salida de `yt-dlp` de cada `Attempt`, con un límite fijo.
- [ ] Un endpoint devuelve ese detalle para un job; los jobs sin detalle responden de forma clara.
- [ ] La tarjeta de un job `failed` muestra "Ver detalle" y lo despliega.
- [ ] Reintentar o quitar el job del historial descarta el detalle anterior.
- [ ] Tests con `FakeEngine` que falla con stderr conocido, y tests de componente.
