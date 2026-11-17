---
status: accepted
---

# La carpeta de descargas se puede cambiar con el diálogo nativo

Sustituye la parte de "destino fijo" de ADR-0007. Las opciones de descarga siguen siendo las de nivel 1.

La carpeta de descargas es `~/Downloads` por defecto. El usuario puede elegir otra desde el menú del engranaje, con el diálogo de carpetas del sistema (Finder en macOS, Explorador en Windows), y volver a la de por defecto. La elección se guarda en SQLite, en `$DATA_DIR`, así que sobrevive a las actualizaciones de la app.

Cada job guarda la carpeta en la que se puso en cola. Cambiar la carpeta afecta solo a lo que se ponga en cola después; lo que ya está en cola o en curso, y sus reintentos, terminan en la carpeta anterior. Así una playlist no queda repartida entre dos carpetas.

## Considered Options

- **Campo de texto con la ruta**: descartado. Es incómodo y propenso a errores de escritura.
- **API de archivos del navegador (File System Access)**: descartada. No da la ruta real, y Safari y Firefox no la implementan. Además, quien escribe los archivos es el servidor, no el navegador.
- **Diálogo nativo abierto por el servidor**: elegida. El servidor corre en el equipo del usuario y puede abrir el diálogo del sistema (`osascript` en macOS, PowerShell con `FolderBrowserDialog` en Windows).
- **Si la carpeta elegida no existe al descargar, usar Descargas**: descartada. Guardar en otro sitio sin avisar confunde. La app avisa al poner en cola y la descarga falla con un mensaje claro.

## Consequences

- La carpeta elegida debe existir: la app no la crea, para no crear por error una carpeta normal donde debería estar un disco externo desconectado. Las subcarpetas de playlist sí se crean, y `~/Downloads` también, como antes.
- En el Docker de desarrollo no hay diálogo nativo: la API responde 501 y existe un `PUT` con la ruta para pruebas.
