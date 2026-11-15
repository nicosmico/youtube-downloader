# 08: Presets

**What to build:** El usuario puede crear, aplicar, renombrar y eliminar `Preset` desde la UI. Cada preset combina `DownloadMode` con `Quality` o `AudioFormat`. Se siembran `Mejor video` y `MP3` solo si la tabla está vacía. Los nombres son únicos y las combinaciones inválidas se rechazan.

**Blocked by:** 07 (Opciones nivel 1).

**Status:** ready-for-agent

- [ ] Los presets persisten entre reinicios.
- [ ] Aplicar un preset configura modo y calidad en un clic.
- [ ] El seed ocurre solo con la tabla vacía.
- [ ] Los nombres duplicados se rechazan con un mensaje claro.
- [ ] Las combinaciones inválidas se rechazan.
- [ ] Tests de API y de UI con transporte mockeado.
