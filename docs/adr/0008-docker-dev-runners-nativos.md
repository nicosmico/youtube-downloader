---
status: accepted
---

# Docker para desarrollo y runners nativos para empaquetar

La app es un ejecutable de escritorio para macOS y Windows, pero el entorno de desarrollo no debe exigir Python instalado en el Mac del autor. Decidimos usar Docker Compose (OrbStack) para el backend y los tests, dejar Angular en Node local (o contenedor opcional), y construir los ejecutables en GitHub Actions con runners macOS y Windows. El producto nunca corre dentro de Docker.

## Considered Options

- **`uv` + venv local**: más liviano, pero sin paridad con CI y requiere Python en el host.
- **Docker también para empaquetar**: inviable; los contenedores son Linux y PyInstaller no cross-compila a macOS ni Windows.
- **Compilar localmente**: requiere Python en macOS y una máquina Windows.

## Consequences

- `DOWNLOAD_DIR`, `DATA_DIR` y `ENGINE_BIN_DIR` se pueden sobrescribir por entorno; en producción los defaults siguen siendo `~/Downloads`, `~/.youtube-downloader` y su subcarpeta `bin`.
- En el contenedor el servidor debe escuchar en `0.0.0.0` con un puerto fijo para que el puerto publicado sea alcanzable; `BIND_HOST` y `PORT` lo permiten solo en desarrollo. Compose publica ese puerto únicamente en `127.0.0.1` del host, y la validación de `Host` acepta ese puerto.
- En desarrollo, abrir el navegador y "abrir carpeta" son responsabilidad del host; el contenedor no puede hacerlo.
- El `Engine` usa binarios Linux solo en desarrollo y CI; Linux no es plataforma soportada para usuarios finales.
- Las plataformas de distribución son macOS arm64 (Apple Silicon) y Windows x64. `macos-latest` compila arm64 y no se produce build universal2 ni Intel.
- Las versiones se publican como GitHub Releases por tag, con un `.zip` por plataforma; los artefactos de Actions quedan para builds de prueba.
- Docker/OrbStack pasa a ser requisito de desarrollo, no del usuario final.
