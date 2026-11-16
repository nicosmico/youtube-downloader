# 03: "Mostrar archivo" no funciona en Windows

**What to build:** En Windows, "Mostrar archivo" no selecciona el archivo en el Explorador, aunque "Abrir carpeta" sí funciona (hallazgo en un PC real, 2026-11-16). Causa: `subprocess.Popen(["explorer", f"/select,{path}"])` entrecomilla el argumento entero cuando la ruta tiene espacios (`"/select,C:\…\a b.mp3"`) y Explorer lo ignora. Hay que pasar la línea de comandos `explorer /select,"<ruta>"`.

**Blocked by:** None.

**Status:** ready-for-agent

- [x] `reveal_file` en Windows pasa `explorer /select,"<ruta>"` como línea de comandos.
- [x] Test por plataforma sin lanzar procesos.
- [ ] Verificado en un PC con Windows real (lo prueba el usuario con la v0.2.3).

## Comments

2026-11-16: Hecho por el orquestador en `backend/app/opener.py`, con `backend/tests/test_opener.py`. Los nombres de Windows no pueden contener `"`, así que entrecomillar la ruta es seguro.
