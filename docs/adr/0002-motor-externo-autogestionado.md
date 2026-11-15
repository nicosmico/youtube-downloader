---
status: accepted
---

# El `Engine` vive fuera del ejecutable

YouTube cambia con frecuencia y un `yt-dlp` congelado dentro del binario deja de funcionar en semanas. Decidimos que el ejecutable no empaquete el `Engine`: en el primer arranque descarga `yt-dlp`, `ffmpeg`, `ffprobe` y Deno en `~/.youtube-downloader/bin`, y actualiza `yt-dlp` por su cuenta (al iniciar si pasaron más de 24 h, cada 24 h mientras la app está abierta, o por acción del usuario).

Desde `yt-dlp` 2025.11.12, el soporte completo de YouTube exige un runtime JavaScript externo para resolver los desafíos del reproductor. Elegimos Deno, gestionado por la app como un binario más del `Engine`.

## Considered Options

- **Usar Node u otro runtime si el usuario ya lo tiene**: descartado; rompe la promesa de no requerir instalaciones, y `yt-dlp` desactiva por defecto los runtimes distintos de Deno por seguridad.
- **Empaquetar Deno dentro del ejecutable**: descartado; engorda el binario y obliga a recompilar la app para actualizarlo, sin ventaja frente a gestionarlo como el resto del `Engine`.
- **Actualizar con `yt-dlp -U`**: descartado tras el spike 01. En Windows, `-U` deja un `yt-dlp.exe.old` que sigue bloqueado mientras un job lo use, y la siguiente actualización falla con `Unable to remove the old version`. Además no deja a la app registrar el hash instalado.

## Consequences

- El primer arranque requiere red y puede fallar; la UI debe mostrar el estado "preparando motor" con opción de reintentar.
- El ejecutable queda liviano y el motor se actualiza sin recompilar la app.
- Cada binario se verifica por SHA-256 antes de activarse: `yt-dlp` contra el `SHA2-256SUMS` de su release; `ffmpeg`, `ffprobe` y Deno contra hashes fijados en el código para una versión concreta.
- Las fuentes con hash fijado deben ser releases versionados y permanentes: martin-riedl para macOS y Linux, y Gyan (`GyanD/codexffmpeg`) para Windows. BtbN se descarta porque borra sus releases antiguos.
- La actualización de `yt-dlp` reutiliza el camino de instalación (descarga, verificación, intercambio de archivos) y solo ocurre con la `Queue` en pausa y sin jobs activos, para que ningún proceso retenga el binario viejo.
- Deno es obligatorio: si falta o no arranca, el `Engine` queda en `error` en lugar de descargar con formatos degradados.
- `ffmpeg`, `ffprobe` y Deno solo cambian de versión con una nueva versión de la app; `yt-dlp` se actualiza solo.
- Los binarios se resuelven para macOS arm64 y Windows x64 en producción, y para Linux arm64 (desarrollo en Apple Silicon) y x64 (CI).
