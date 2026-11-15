# 06: Cola persistente y concurrencia

**What to build:** Varios `DownloadJob` conviven en una `Queue` FIFO con un máximo de dos ejecuciones simultáneas. Los estados se persisten: los `queued` se reanudan al reiniciar, y los que estaban `downloading` o `processing` pasan a `interrupted`. La UI muestra varias tarjetas de cola y se actualiza con `queue.updated`.

**Blocked by:** 05 (Descarga de un video end-to-end), 14 (Smoke de empaquetado nativo).

**Status:** ready-for-agent

- [ ] Con cinco jobs encolados nunca hay más de dos activos.
- [ ] El orden FIFO se respeta.
- [ ] Un reinicio conserva `queued`, `completed` y `failed`.
- [ ] Los jobs activos al cerrar quedan `interrupted`.
- [ ] Los `queued` se reanudan automáticamente tras reiniciar.
- [ ] La UI refleja la cola y los estados sin recargar.
- [ ] Una actualización del Engine pausa el despacho, espera a que terminen los jobs activos, intercambia el binario y reanuda la `Queue` (ADR-0002).
- [ ] Tests de concurrencia y persistencia con SQLite temporal.
