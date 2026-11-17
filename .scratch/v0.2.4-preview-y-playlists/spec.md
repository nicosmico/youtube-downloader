# Spec: v0.2.4 — preview rápido y playlists

**Status:** in-progress

## Problem Statement

Pruebas de la v0.2.3 en un Mac real (2026-11-16):

1. "Obteniendo información" tarda unos 18 s por vídeo. Medido: 15 s son solo el arranque de `yt-dlp` (`yt-dlp --version` tarda lo mismo, sin red). El asset `yt-dlp_macos` es un ejecutable PyInstaller de un solo archivo: en cada ejecución se descomprime en una carpeta temporal nueva y macOS revisa esas librerías antes de cargarlas (proceso esperando con 0 % de CPU). En Windows, `yt-dlp.exe` hace lo mismo y Defender revisa la carpeta temporal. Con el asset sin empaquetar (`yt-dlp_macos.zip`) el primer arranque tarda lo mismo (macOS lo revisa una vez) y después **0,15 s**; el preview completo de un vídeo baja de 18 s a **2 s**.
2. Un vídeo que viene de una playlist solo se puede descargar suelto, o abrir la playlist y elegir.
3. El botón "Descargar N videos" dice "videos" aunque se descargue audio.
4. Una playlist del listado no se puede cancelar ni reintentar entera.
5. Las descargas con error se reintentan de una en una.
6. No hay una forma rápida de ir a YouTube a buscar el enlace.
7. Los vídeos no disponibles de una playlist aparecen en gris en la selección; no aportan nada.
8. Después de "Descargar", el enlace y el preview se quedan; hay que borrarlos a mano para pegar otro.

## Solution

1. El Engine instala la versión sin empaquetar de yt-dlp en macOS y Windows (ticket 01).
2. Vídeo de una playlist: botones "Descargar 1" y "Descargar N" (ticket 02).
3. "Descargar N", sin "videos" (ticket 02).
4. Menú de la playlist en el listado: "Cancelar descargas" y "Reintentar fallidas" (ticket 03).
5. Filtro "Con error": selección y "Reintentar (N)" (ticket 03).
6. Botón "Ir a YouTube" junto al campo de la URL (ticket 02).
7. Los vídeos no disponibles no aparecen en la selección de la playlist (ticket 02).
8. Al poner en cola, el campo se vacía y el preview se cierra (ticket 02).

## User Stories

1. Como usuario, quiero ver el preview en un par de segundos.
2. Como usuario que pega un vídeo de una playlist, quiero descargar ese vídeo o la playlist entera con un clic.
3. Como usuario, quiero que los botones no digan "videos" cuando descargo audio.
4. Como usuario, quiero cancelar todo lo pendiente de una playlist, o reintentar lo que falló, sin ir vídeo a vídeo.
5. Como usuario, quiero elegir varias descargas con error y reintentarlas juntas.
6. Como usuario, quiero ir a YouTube desde la app para buscar el enlace.
7. Como usuario, quiero ver en la selección de la playlist solo lo que se puede descargar.
8. Como usuario, quiero que después de "Descargar" la app quede lista para el siguiente enlace.

## Implementation Decisions

Detalle en cada ticket. Resumen:

- **Ticket 01 — yt-dlp sin empaquetar (backend, Engine).** macOS usa `yt-dlp_macos.zip` y Windows `yt-dlp_win.zip`; Linux (Docker de desarrollo) sigue con el binario único. Se instala la carpeta completa (ejecutable + `_internal/`), verificada con el SHA-256 del zip que publica `SHA2-256SUMS`. La actualización cambia la carpeta entera con el mismo esquema `.new`/`.old` y rollback. Una instalación existente con el binario viejo se migra sola.
- **Ticket 02 — Preview (frontend + `preview/playlists.py`).** Puntos 2, 3, 6, 7 y 8.
- **Ticket 03 — Listado (backend jobs + frontend downloads).** Puntos 4 y 5: endpoints para cancelar y reintentar una playlist y para reintentar varias descargas.

Textos en español, sin explicar la UI. Sin cambios de dependencias.

## Testing Decisions

- Mismos criterios de siempre: deterministas, sin red, reloj inyectado.
- El smoke test empaquetado de CI instala el Engine real en macOS y Windows: es la prueba de punta a punta del ticket 01.

## Out of Scope

- Detectar antes de descargar los vídeos bloqueados por país o edad: la lista de YouTube no lo dice y comprobarlo vídeo a vídeo alargaría el preview.
- Mantener un proceso de yt-dlp vivo entre previews.

## Further Notes

- Se publica como `v0.2.4`.
