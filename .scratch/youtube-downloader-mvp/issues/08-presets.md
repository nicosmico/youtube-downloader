# 08: Presets

**What to build:** El usuario puede crear, aplicar, renombrar y eliminar `Preset` desde la UI. Cada preset combina `DownloadMode` con `Quality` o `AudioFormat`. Se siembran `Mejor video` y `MP3` solo si la tabla está vacía. Los nombres son únicos y las combinaciones inválidas se rechazan.

**Blocked by:** 07 (Opciones nivel 1).

**Status:** resolved

- [x] Los presets persisten entre reinicios.
- [x] Aplicar un preset configura modo y calidad en un clic.
- [x] El seed ocurre solo con la tabla vacía.
- [x] Los nombres duplicados se rechazan con un mensaje claro.
- [x] Las combinaciones inválidas se rechazan.
- [x] Tests de API y de UI con transporte mockeado.

## Comments

**2026-11-15 — Implementación.**

- **Persistencia**: migración 2 crea `presets` según la spec (`name` UNIQUE, `mode` con CHECK). El seed (`Mejor video`: video/best, `MP3`: audio/mp3) corre en cada arranque de `create_app` y solo inserta si la tabla está vacía. **Consecuencia**: si el usuario borra todos los presets, reaparecen los dos por defecto en el siguiente arranque (no hay marca de "ya sembrado"; es la lectura literal de "solo si la tabla está vacía"). Sembrar dentro de la migración evitaría esto, pero entonces las bases de datos creadas antes de este ticket nunca recibirían el seed y borrar los presets por defecto sería permanente; no se eligió porque la spec habla de "tabla vacía", no de "primera vez".
- **API** (`presets/api.py`, `presets/repository.py`): `GET` devuelve una lista simple ordenada por nombre sin distinguir mayúsculas ni acentos; `POST` → `201`; `PATCH` parcial; `DELETE` → `204`. Nombre recortado, 1–40 caracteres (`422 invalid_name`); duplicado sin distinguir mayúsculas (`casefold`, también Unicode) → `409 preset_name_taken`, comprobado bajo lock porque el `UNIQUE` de SQLite distingue mayúsculas; id desconocido → `404 preset_not_found`. Renombrar un preset a su propio nombre con otra capitalización está permitido.
- **Validador compartido**: `jobs/options.py` (`check_options` y los tipos `Mode`/`QualityName`/`AudioFormatName`) lo usan `POST /api/jobs` y los presets; se movió desde `jobs/api.py` sin cambiar mensajes.
- **PATCH de opciones**: si llega `mode`, `quality` o `audioFormat`, el grupo de opciones se reemplaza entero (lo que falta queda vacío) y se valida, así cambiar de modo nunca deja un campo viejo. Un `PATCH` solo con `mode` sin sus opciones da `422 invalid_options`.
- **UI** (`presets/presets.*`, hijo de la tarjeta de preview): botones por preset (un clic aplica modo + calidad/formato), "Guardar como preset" con campo en línea (Enter guarda, Escape cancela), "Gestionar" con renombrar en línea y eliminar con paso de confirmación. Los errores del servidor (duplicado, opciones inválidas, red) se muestran en español. Si el video no ofrece la calidad del preset, cae a `best` como en el ticket 07. `PresetsService` se carga en `App.ngOnInit`.
- **Desviaciones menores**: códigos nuevos `invalid_name` y `preset_not_found` (la spec solo fija `preset_name_taken` e `invalid_options`); `GET /api/presets` devuelve un array, no un objeto.
- **Verificación**: 494 pytest, ruff, 150 Vitest y build en verde. Real con `docker compose up --build` y curl: seeds, crear (nombre recortado), duplicado `409` (también con otra capitalización), combinación inválida `422`, renombrar a nombre existente `409`, cambiar formato, `404`, borrar `204`; tras `docker compose restart` los cambios persisten. La UI solo se probó con tests de componente (no en navegador).

**2026-11-15 — Revisión del orquestador.** Checks repetidos (494 backend, 150 frontend, ruff, build). Probado en el navegador integrado: aplicar `MP3` cambia a audio con MP3; guardar `mp3` muestra "Ya existe un preset con ese nombre. Elige otro."; guardar `Video 720p` lo añade; borrarlo desde "Gestionar" pide confirmación y lo quita. Spec actualizada con el seed en cada arranque y los códigos de presets.

**2026-11-15 — Resuelto.** CI `43765191613` y Native `43765191600` verdes.
