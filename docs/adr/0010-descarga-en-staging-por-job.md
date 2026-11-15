---
status: accepted
---

# Cada `Attempt` descarga en su propia carpeta temporal

Con dos descargas simultáneas, dos `DownloadJob` con el mismo título podían elegir el mismo nombre final. Además, calcular ese nombre de antemano obligaba a replicar cómo `yt-dlp` sanea los nombres de archivo en cada sistema. Decidimos que cada `Attempt` descargue en `$DATA_DIR/staging/<job_id>/` y que, al terminar, la app mueva el archivo a la `Destination`, resolviendo colisiones con ` (2)`, ` (3)`… bajo un lock propio.

## Considered Options

- **Comprobar el nombre al despachar**: descartada por la carrera entre jobs concurrentes y por depender del saneado de `yt-dlp`.
- **Incluir el ID del video en el nombre**: descartada; evita colisiones pero ensucia los nombres que ve el usuario.

## Consequences

- `completed` significa que el archivo ya está en la `Destination`, nunca en staging.
- Cancelar o fallar borra la carpeta de staging del job; reintentar empieza con una carpeta limpia, así que no se duplican archivos.
- Al arrancar se limpian las carpetas de staging sin un job activo.
- `$DATA_DIR` y `DOWNLOAD_DIR` pueden estar en volúmenes distintos; el movimiento final debe tolerar una copia seguida de un borrado, no solo un `rename`.
