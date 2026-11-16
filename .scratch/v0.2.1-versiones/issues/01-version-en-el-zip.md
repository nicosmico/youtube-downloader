# 01: Versión en el nombre del zip

**What to build:** En `.github/workflows/native.yml`, el zip pasa a llamarse `YouTube-Downloader-<versión>-<plataforma>.zip`. La versión se lee de `backend/app/__init__.py` (`__version__`) en todos los builds. En un build de tag, el job falla si el tag no es `v<__version__>`. `APP_VERSION`, la metadata de PyInstaller, sale de la misma fuente. Los pasos de zip, tamaño, upload-artifact y Release usan el nombre nuevo. El `.app` y la carpeta de Windows no cambian de nombre. Actualizar el README si menciona el nombre del zip. Ver la spec, sección "Nombre del zip".

**Blocked by:** None (can start immediately).

**Status:** ready-for-agent

- [ ] El build de una rama produce `YouTube-Downloader-<__version__>-macos-arm64.zip` y `…-windows-x64.zip` como artefactos.
- [ ] Un tag que no coincide con `__version__` hace fallar el job antes de construir.
- [ ] El job de Release publica los dos zips con el nombre nuevo.
- [ ] Los smoke tests siguen pasando en macOS y Windows.

## Comments
