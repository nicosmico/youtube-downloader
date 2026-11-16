# 01: Idle Shutdown rápido tras cerrar la pestaña

**What to build:** `Idle Shutdown` pasa a 15 s tras desconectarse el último cliente SSE (nuevo valor por defecto de `IDLE_SHUTDOWN_SECONDS`), con 60 s de gracia al arrancar hasta que se conecta la primera pestaña. Las condiciones de inactividad no cambian y `0` sigue desactivándolo. El smoke test empaquetado fija un `IDLE_SHUTDOWN_SECONDS` alto para no cerrarse entre pasos, y gana un caso que comprueba el cierre automático tras abrir y cerrar una conexión SSE con un timeout pequeño. Actualizar `GLOSSARY.md` (`Idle Shutdown`) y el ADR-0001; el README lo actualiza el orquestador. Ver la spec, sección "Idle Shutdown rápido".

**Blocked by:** None (can start immediately).

**Status:** resolved

- [x] Cierre unos 15 s después de cerrar la última pestaña, sin descargas ni trabajo del motor.
- [x] 60 s de gracia al arrancar sin ninguna pestaña.
- [x] Una reconexión antes del plazo (recarga) cancela el cierre.
- [x] Con descargas activas no se cierra; empieza a contar al vaciarse la `Queue`.
- [x] `IDLE_SHUTDOWN_SECONDS=0` lo desactiva.
- [x] Smoke test: entorno con timeout alto (también en `--reopen`) y caso nuevo de cierre automático.
- [x] Tests de `IdleMonitor` con reloj inyectado; glosario y ADR-0001 actualizados.

## Comments

**2026-11-16: implementación.**

- `app/idle.py`: `IDLE_SHUTDOWN_SECONDS = 15`, `STARTUP_GRACE_SECONDS = 60`, `MAX_POLL_SECONDS = 1`. `IdleMonitor` recuerda si algún cliente SSE se ha conectado alguna vez (en `check()` y en `touch()`, así una pestaña que entra y sale entre dos sondeos también cuenta); mientras no, el plazo es `max(60, timeout)` (`effective_timeout`). Condiciones, reinicio por eventos y `0` sin cambios (config y wiring de `main.py` no necesitaron tocarse; el default sale de `idle.py`). Con trabajo en curso `_since` se reinicia en cada sondeo, así los 15 s cuentan desde que la `Queue` se vacía.
- `packaging/smoke.py`: `IDLE_SHUTDOWN_SECONDS=600` en el entorno del flujo principal y de `--reopen` (añadido a las claves de `open --env`). Caso nuevo `run_idle_shutdown`, al final del flujo principal (no en `--empty-ca-store`): arranca de nuevo con los mismos datos (Engine ya instalado: una instalación en curso cuenta como trabajo y bloquearía el cierre), `IDLE_SHUTDOWN_SECONDS=3`, abre `GET /api/events` (solo exige `Host`, el GET no necesita la cabecera CSRF), lo mantiene 5 s comprobando que la app sigue viva, lo cierra y espera hasta 30 s a que el proceso salga solo y borre `runtime.json`. Se ejecuta dentro del paso "Smoke test" existente de `native.yml` en macOS y Windows; no hizo falta tocar el workflow. Coste: arranque + ~9 s. Códigos de salida intactos (10 sigue siendo solo bot check).
- `GLOSSARY.md`, ADR-0001 (con el motivo: actualizar exige que la versión vieja ya no esté) y el comentario de `compose.yaml` (600 -> 15).
- Desviaciones: ninguna de fondo. Queda un comentario obsoleto "10 minutes" en `frontend/src/app/app.ts:13` (fuera de alcance) y el README (lo hace el orquestador).

**Verificación:** `docker compose run --rm tests` 722 passed (3 deselected), `ruff check` y `ruff format --check` limpios. Tests nuevos/actualizados en `test_idle.py` (reloj inyectado): 15 s tras la última pestaña, 60 s de gracia, plazo configurado mayor que la gracia, paso de gracia a 15 s al conectarse la primera pestaña, pestaña que entra y sale entre sondeos, reconexión antes del plazo, trabajo activo (también durante la gracia) y cuenta posterior, `0` desactivado, intervalo de sondeo, y los tests de la app con la gracia. `run_idle_shutdown` probado en Docker contra `python -m app` con binarios del Engine falsos: salió 3,5 s después de cerrar la conexión SSE, exit 0.

**Solo CI puede verificar:** el binario empaquetado real (PyInstaller) en macOS y Windows con el Engine instalado de verdad, y el modo `--reopen` con `open --env IDLE_SHUTDOWN_SECONDS=600`. Falta marcar la casilla del smoke hasta que pase en CI.

**2026-11-16 — Resuelto.** Publicado en `v0.2.3` (Native/Release `43967590958`; en main, CI `43967239573` y Native `43967239567`, con el caso de Idle Shutdown del smoke pasando en macOS y Windows). El relevo de versión se probó de punta a punta en Docker: una instancia "0.1.0" se cerró y la 0.2.2 tomó su lugar.
