# Spec: v0.2.3 — cierre al cerrar la pestaña y relevo de versión

**Status:** resolved

## Problem Statement

Prueba de la actualización de v0.2.1 a v0.2.2 en un Mac real (2026-11-16): la v0.2.1 seguía corriendo en segundo plano porque `Idle Shutdown` tarda 10 minutos. Al abrir la v0.2.2, extraída en la misma carpeta, macOS dio el error `-47` ("archivo ocupado"). Aunque se hubiera abierto, `Single Instance` habría reutilizado la instancia vieja, y el usuario habría seguido en la v0.2.1 sin saberlo.

## Solution

- La app se cierra unos 15 segundos después de que se cierre la última pestaña, si no hay descargas ni trabajo del motor en curso.
- Al abrir una versión nueva mientras una anterior sigue corriendo, la nueva le pide que se cierre y toma el relevo.
- Las instrucciones de actualización dicen que hay que cerrar la app antes de reemplazarla.

## User Stories

1. Como usuario, quiero que la app se cierre sola poco después de cerrar su pestaña, para no dejar un proceso invisible.
2. Como usuario, quiero que recargar la pestaña o que el Mac despierte del reposo no cierre la app.
3. Como usuario, quiero que una descarga en curso termine aunque cierre la pestaña.
4. Como usuario que actualiza, quiero que al abrir la versión nueva se use esa versión, aunque la anterior siguiera abierta.

## Implementation Decisions

### Idle Shutdown rápido

- Las condiciones de "inactiva" no cambian: sin clientes SSE, sin jobs `queued`/`downloading`/`processing` y sin instalación o actualización del Engine en curso. Lo que cambia es el tiempo:
  - **Tras la última pestaña: 15 s.** Valor por defecto de `IDLE_SHUTDOWN_SECONDS` (antes, 600).
  - **Arranque: 60 s de gracia** para que se conecte la primera pestaña. Los 15 s no aplican hasta que se ha conectado algún cliente SSE. Si nunca se conecta ninguno, se usa `max(60, timeout)`.
- Cualquier evento (un job o el Engine que cambia) sigue reiniciando el temporizador. Si la última pestaña se cierra durante una descarga, la app se cierra 15 s después de que la `Queue` quede vacía.
- `IDLE_SHUTDOWN_SECONDS=0` sigue desactivándolo (Docker de desarrollo).
- `MAX_POLL_SECONDS` y `poll_seconds` deben permitir reaccionar en torno a 15 s; un sondeo cada segundo como mucho basta.
- El smoke test empaquetado (`packaging/smoke.py`) no tiene ninguna pestaña conectada. Para que no se cierre entre pasos, fija `IDLE_SHUTDOWN_SECONDS` explícitamente a un valor alto en su entorno, también en el modo `--reopen`, que pasa el entorno con `open --env`. Añade además un caso que compruebe el cierre automático: con un timeout pequeño, abre y cierra una conexión SSE y comprueba que el proceso termina solo.
- Se actualizan el glosario (`Idle Shutdown`) y el ADR-0001, que dicen "10 minutos".

### Relevo de versión (Single Instance)

- `probe_health` devuelve, además de "es esta app", la `version` que informa `/api/health`.
- En `acquire_instance`, cuando hay una instancia sana:
  - Su versión es **igual o mayor** que la propia: `Reuse`, como hoy. No se cambia a una versión más vieja.
  - Su versión es **menor** (comparación numérica `X.Y.Z`; reutilizar `app.updates.is_newer`), o no informa versión: relevo.
    1. `POST /api/system/shutdown` a la instancia vieja, con la cabecera `X-Requested-With: youtube-downloader`.
    2. Esperar a que suelte el `instance.lock` (con un límite de unos 15 s; el cierre ordenado ya interrumpe descargas y cierra conexiones SSE).
    3. Seguir como `Start`: limpiar el `runtime.json` viejo si sigue ahí y arrancar el servidor.
  - Si la vieja no se cierra a tiempo: registrar un aviso y hacer `Reuse` de la vieja. Es mejor que fallar.
- Las pestañas abiertas de la versión vieja ya reciben `shutdown {"reason": "user"}` y muestran la pantalla de cierre. El navegador abre una pestaña nueva con la versión nueva.
- Al cerrar, la instancia vieja deja como `interrupted` las descargas activas, y las encoladas se reanudan en la nueva (comportamiento actual de `queue.start()`). No se añade reanudación automática de las interrumpidas.
- Aplica igual en macOS (el lanzador desacoplado ejecuta el mismo `run`) y en Windows.
- Se registra en el log: "Taking over from version X (running Y)".

### Instrucciones de actualización

- README, sección "Descargar e instalar": cómo actualizar. Cerrar la app ("Cerrar aplicación" o cerrar su pestaña y esperar unos segundos), reemplazar la app (en macOS, en Aplicaciones) y abrirla. Los datos se conservan.
- Las notas de cada Release empiezan con esas mismas instrucciones breves, desde `packaging/release-notes.md`, con `gh release create --notes-file … --generate-notes`. Esto lo hace el orquestador en la integración.

## Testing Decisions

- Mismos criterios de siempre: deterministas, sin red y con reloj inyectado.
- `IdleMonitor`:
  - 15 s tras desconectarse el último cliente.
  - 60 s de gracia sin clientes desde el arranque.
  - Una reconexión antes del plazo cancela el cierre.
  - Un job activo lo impide, y al terminar empiezan a contar 15 s.
  - `0` lo desactiva.
- `acquire_instance` con `probe` y `shutdown` falsos:
  - Misma versión y versión mayor: `Reuse`.
  - Versión menor y sin versión: pide el cierre y hace `Start` al soltarse el lock.
  - Si la vieja no se cierra a tiempo: `Reuse`.
- Smoke test empaquetado en CI: sigue pasando, más el caso de cierre automático.

## Out of Scope

- Reanudar automáticamente las descargas interrumpidas por un relevo.
- Evitar el error `-47` de Finder: ocurre antes de que se ejecute la app; se cubre con las instrucciones.
- Actualización automática (ADR-0011).

## Further Notes

- Se publica como `v0.2.3`.
