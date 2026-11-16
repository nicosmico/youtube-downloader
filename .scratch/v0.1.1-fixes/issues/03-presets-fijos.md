# 03: Presets fijos ("Mejor video" y "MP3")

**What to build:** Los presets se reducen a dos atajos fijos de un clic, "Mejor video" (video, `best`) y "MP3" (audio, `mp3`), junto a los selectores de modo, calidad y formato, que siguen visibles. Se eliminan "Guardar como preset", "Gestionar", renombrar y borrar; la API `/api/presets`; y la tabla `presets` mediante una migración nueva. Los dos atajos pasan a ser constantes del frontend. Ver la sección "Presets fijos" de la spec.

**Blocked by:** None (can start immediately).

**Status:** ready-for-agent

- [x] La UI muestra solo los dos atajos y aplicarlos sigue respetando el fallback a `best` del ticket 07 del MVP.
- [x] No quedan "Guardar como preset" ni "Gestionar".
- [x] `/api/presets` responde 404; una base de datos de la v0.1.0 migra y queda sin la tabla `presets`.
- [x] Se eliminan el código y los tests de presets que ya no aplican.
- [x] Glosario (`Preset` como atajo fijo), spec del MVP (historias 11 a 13 descartadas, API y esquema) y README actualizados.
