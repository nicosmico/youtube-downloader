# 05: "Ver detalle" en jobs fallidos

**What to build:** Cada job `failed` muestra un enlace "Ver detalle" que despliega las últimas líneas de salida de `yt-dlp` (stdout y stderr) de su último `Attempt`, para entender por qué falló más allá del mensaje saneado. La salida se guarda acotada por `Attempt` y se descarta con un reintento o al quitar el job del historial. Ver la sección "Registros" de la spec.

**Blocked by:** None (can start immediately).

**Status:** ready-for-agent

- [x] El runner guarda las últimas líneas de salida de `yt-dlp` de cada `Attempt`, con un límite fijo.
- [x] Un endpoint devuelve ese detalle para un job; los jobs sin detalle responden de forma clara.
- [x] La tarjeta de un job `failed` muestra "Ver detalle" y lo despliega.
- [x] Reintentar o quitar el job del historial descarta el detalle anterior.
- [x] Tests con `FakeEngine` que falla con stderr conocido, y tests de componente.
