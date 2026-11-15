# 02: Walking skeleton en Docker

**What to build:** El esqueleto ejecutable del producto corriendo en Docker Compose: FastAPI sirve el shell de Angular, expone `/api/health`, aplica `Single Instance`, apagado ordenado y validaciones de seguridad. El host abre el navegador en el puerto publicado. GitHub Actions ejecuta la suite con la misma imagen. Todavía no hay binario nativo; eso llega en los tickets de empaquetado.

**Blocked by:** 01 (Spike — Engine, Docker y empaquetado).

**Status:** ready-for-agent

- [ ] `docker compose up` levanta el backend y sirve el shell de Angular en el puerto publicado.
- [ ] El host abre el navegador y ve el shell; el contenedor corre con `OPEN_BROWSER=0`.
- [ ] `/api/health` responde versión, estado del Engine y puerto.
- [ ] Una segunda instancia reutiliza la existente o se documenta el comportamiento en Compose.
- [ ] "Cerrar aplicación" apaga el servidor y limpia `runtime.json`.
- [ ] Peticiones con `Host` no local o mutaciones sin la cabecera de la app son rechazadas.
- [ ] GitHub Actions corre los tests en el mismo contenedor y queda verde.
- [ ] Los tests corren sin Python instalado en el host.
