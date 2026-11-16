---
status: accepted
---

# La app avisa de versiones nuevas, pero no se actualiza sola

La app es portable: un zip con el `.app` (macOS) o con una carpeta y su `.exe` (Windows), sin instalador. Los datos del usuario viven aparte, en `$DATA_DIR`, y la base de datos se migra al arrancar. Por eso actualizar es reemplazar la app por la nueva.

Decidimos que la app compruebe al arrancar el último Release publicado y, si es más nuevo, muestre un aviso con un enlace a su página. El usuario descarga el zip y reemplaza la app a mano. El nombre del `.app` y el de la carpeta de Windows no llevan versión, para que reemplazar funcione. La versión va en el nombre del zip.

## Considered Options

- **Actualización automática (descargar, reemplazar y reiniciar)**: descartada por ahora.
  - En macOS, la app tiene una firma ad-hoc: un bundle descargado por la propia app y puesto en lugar del anterior arriesga problemas con Gatekeeper y la cuarentena.
  - En Windows no se puede reemplazar el `.exe` en ejecución, así que haría falta un proceso auxiliar.
  - Mucho coste y riesgo para una app que se actualiza poco.
- **Instalador, Homebrew o winget**: descartadas mientras la app no esté firmada con un certificado de desarrollador.
- **Sin aviso**: descartada; el usuario no tiene forma de saber que hay una versión nueva.

## Consequences

- La comprobación usa la redirección de `github.com/.../releases/latest`, igual que la de `yt-dlp`: sin la API de GitHub, sin tokens y sin su límite de 60 peticiones por hora.
- Si la comprobación falla, no se muestra nada y la app funciona igual.
- Cada Release debe tener un tag `vX.Y.Z` igual a `__version__`; el workflow lo exige.
