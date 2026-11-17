# Spec: v0.2.6 — playlists plegables y descargas más rápidas

**Status:** resolved

## Problem Statement

Pruebas de la v0.2.5 (2026-11-17):

1. Las playlists del historial ocupan mucho: todas sus filas se ven siempre.
2. Medido en un Mac con una canción de 2 min: la descarga tarda 3,5 s, y 2,6 s de ellos son `yt-dlp` volviendo a pedir a YouTube la información que el preview acaba de obtener. Reutilizándola (`--load-info-json`), la misma descarga tarda 0,9 s.
3. En un vídeo de una playlist, la app ya carga la playlist en segundo plano, pero "Ver playlist completa" la vuelve a pedir (unos 2 s más), y "Descargar N" no se puede pulsar hasta que termina esa carga.

## Solution

1. Playlists plegables en el historial (ticket 01).
2. La descarga de un vídeo suelto reutiliza la información de su preview si es reciente (ticket 02).
3. "Ver playlist completa" usa la playlist ya cargada, y "Descargar playlist" se puede pulsar mientras carga (ticket 03).

## User Stories

1. Como usuario, quiero plegar las playlists del historial para ver más cosas a la vez.
2. Como usuario, quiero que una descarga empiece en cuanto pulso "Descargar".
3. Como usuario, quiero ver la playlist completa al instante y poder pedir su descarga sin esperar.

## Implementation Decisions

Detalle en cada ticket. Los tres se hacen en paralelo: no comparten archivos salvo `core/texts.ts` (cambios localizados).

## Testing Decisions

- Mismos criterios de siempre: deterministas, sin red, reloj inyectado.
- El orquestador mide la mejora de 2 con la app real.

## Out of Scope

- Porcentaje de carga del preview: `yt-dlp` no informa de su avance.
- Reintento automático ante errores de red.
- Más de 2 descargas simultáneas.

## Further Notes

- Se publica como `v0.2.6`.
