# Spec: v0.2.1 — versiones y aviso de actualización

**Status:** resolved

## Problem Statement

La app es portable: se descarga un zip, se descomprime y se ejecuta. Para actualizar, el usuario reemplaza la app por la nueva, y sus datos (`~/.youtube-downloader`) se conservan. Pero hoy no tiene forma de enterarse de que hay una versión nueva. Además, los zips de todos los Releases se llaman igual, así que dos descargas no se distinguen, y la versión instalada no se ve en ningún lugar evidente de la interfaz.

## Solution

Tres cambios acotados:

- El zip de cada Release lleva la versión en el nombre.
- El menú del engranaje muestra la versión instalada.
- La app comprueba al arrancar si hay una versión publicada más nueva y, si la hay, muestra un aviso discreto con un enlace a la página de esa versión.

La app no se actualiza sola (ADR-0011).

## User Stories

1. Como usuario, quiero que el zip descargado diga qué versión es, para no confundir dos descargas.
2. Como usuario, quiero ver qué versión tengo instalada, para saber si estoy al día o decírselo a quien me ayude.
3. Como usuario, quiero que la app me avise cuando hay una versión nueva, con un enlace para descargarla, para no tener que ir a mirar GitHub.

## Implementation Decisions

### Nombre del zip

- Formato: `YouTube-Downloader-<versión>-<plataforma>.zip`, por ejemplo `YouTube-Downloader-0.2.1-macos-arm64.zip`.
- La versión sale de `backend/app/__init__.py` (`__version__`), también en builds de ramas y PRs.
- En un build de tag, el workflow falla si el tag no es exactamente `v<__version__>`, para que nunca se publique un Release con versiones distintas en el tag, el zip y la app.
- `APP_VERSION`, la metadata de PyInstaller, pasa a salir de la misma fuente.
- Ni el `.app` ni la carpeta de Windows cambian de nombre. Un nombre estable es lo que permite actualizar reemplazando.

### Versión en el engranaje

- Al final del menú del engranaje, después de "Cerrar aplicación", aparece una línea discreta y no interactiva: `Versión 0.2.1`.
- Sale de `/api/health` (`version`), que ya existe.

### Aviso de versión nueva

**Backend**
- Al arrancar, en segundo plano y una sola vez, la app pide `https://github.com/nicosmico/youtube-downloader/releases/latest` sin seguir la redirección. Usa el mismo `Fetcher` (`redirect_location`) y el mismo contexto SSL que el Engine. De la `Location` (`…/releases/tag/vX.Y.Z`) obtiene la última versión publicada.
- Compara las versiones como `X.Y.Z` numérico. Solo hay aviso si la publicada es estrictamente mayor que `__version__`.
- Cualquier fallo (sin red, sin Releases, una redirección inesperada, un tag que no es `vX.Y.Z`) se registra en el log como `info` o `warning` y no muestra nada. Nunca bloquea el arranque ni el Engine, y no se reintenta.
- Resultado:
  - `/api/health` gana el campo `update`: `null`, o `{"version": "0.2.2", "url": "https://github.com/nicosmico/youtube-downloader/releases/tag/v0.2.2"}`. La `url` se construye a partir del tag parseado; nunca se copia la `Location` tal cual.
  - Cuando la comprobación encuentra una versión nueva, publica el evento SSE `app.update` con ese mismo objeto, para que las pestañas ya abiertas lo vean sin recargar.
- Se puede desactivar con la variable de entorno `UPDATE_CHECK=0`, para tests y por si hiciera falta. Por defecto está activa, también en Docker.
- No se lee ningún token del entorno y no se envía nada aparte de la petición GET (el User-Agent es el mismo que ya usa el Engine).

**Frontend**
- Si hay `update`, la barra superior muestra un enlace con aspecto de chip junto al indicador del motor: icono de flecha hacia arriba más `v0.2.2`. Abre `url` en una pestaña nueva (`target="_blank"`, `rel="noopener"`).
- Bajo 640 px, solo el icono, con la etiqueta para lectores de pantalla.
- `aria-label` y `title`: "Hay una versión nueva: 0.2.2".
- No hay texto explicativo, ni modal, ni opción de descartar el aviso. Desaparece cuando el usuario instala esa versión.

## Testing Decisions

- Mismos criterios que los lotes anteriores: comportamiento externo, deterministas y sin red.
- Backend:
  - Comparación de versiones (mayor, igual, menor; `0.10.0` > `0.9.0`).
  - Parseo de la `Location`: tag válido, tag no válido, URL inesperada.
  - Con un `Fetcher` falso: sin aviso cuando la versión es igual o menor, aviso cuando es mayor, sin aviso y sin error cuando el `Fetcher` falla.
  - `/api/health` incluye `update`.
  - El evento `app.update` se publica.
  - `UPDATE_CHECK=0` no hace ninguna petición.
- Frontend: tests de componente del chip de actualización (aparece o no, enlace correcto, etiqueta accesible, actualización por SSE) y de la línea de versión del menú.
- Workflow: el build de rama genera `YouTube-Downloader-<__version__>-<plataforma>.zip`. La comprobación tag/versión se ejecuta en el tag del Release.

## Out of Scope

- Actualización automática: descargar, reemplazar y reiniciar (ADR-0011).
- Instaladores (`.dmg`, MSI o instalador de Windows), Homebrew y winget.
- Comprobaciones periódicas mientras la app está abierta. Solo se comprueba al arrancar, y la app se reinicia a menudo por `Idle Shutdown`.
- Notas de la versión dentro de la app.
- Descartar o posponer el aviso.

## Further Notes

- Se publica como `v0.2.1`.
- El aviso solo puede probarse de punta a punta cuando exista un Release posterior al instalado. Hasta entonces se verifica con tests y, en desarrollo, simulando una versión anterior.
