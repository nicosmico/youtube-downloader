# 03: Presets fijos ("Mejor video" y "MP3")

**What to build:** Los presets se reducen a dos atajos fijos de un clic, "Mejor video" (video, `best`) y "MP3" (audio, `mp3`), junto a los selectores de modo, calidad y formato, que siguen visibles. Se eliminan "Guardar como preset", "Gestionar", renombrar y borrar; la API `/api/presets`; y la tabla `presets` mediante una migración nueva. Los dos atajos pasan a ser constantes del frontend. Ver la sección "Presets fijos" de la spec.

**Blocked by:** None (can start immediately).

**Status:** ready-for-agent

- [x] La UI muestra solo los dos atajos y aplicarlos sigue respetando el fallback a `best` del ticket 07 del MVP.
- [x] No quedan "Guardar como preset" ni "Gestionar".
- [x] `/api/presets` responde 404; una base de datos de la v0.1.0 migra y queda sin la tabla `presets`.
- [x] Se eliminan el código y los tests de presets que ya no aplican.
- [x] Glosario (`Preset` como atajo fijo), spec del MVP (historias 11 a 13 descartadas, API y esquema) y README actualizados.

## Comments

**2026-11-15**: implementado en la rama `ticket/v011-app` (sin push).

- Frontend: `PRESETS` (constantes) en `preview/presets.ts` y dos botones junto a los selectores; se borraron el componente `presets`, `PresetsService` y sus tests. `applyPreset` conserva el fallback a `best` (probado con un video sin `best` en `availableQualities`).
- Backend: borrados `app/presets/` y `test_presets_api.py`; migración 4 `DROP TABLE presets`. Test con una base creada con las migraciones 1 a 3 (v0.1.0) y filas en `presets`. `/api/presets` responde 404.
- Docs: glosario (`Preset` = atajo fijo), spec del MVP (historias 11 a 13 tachadas, tabla de la API, esquema y siembra) y README (solo las líneas de presets). ADR-0004 pierde la mención a los presets en su título y texto.
- Verificado: en una app real con la base `.dev-data` de la v0.1.0 (user_version 3, 27 jobs) migró a 5 sin la tabla `presets`; la UI muestra solo "Mejor video" y "MP3".
