---
status: accepted
---

# La app de escritorio es un servidor local que se usa desde el navegador

El producto debía ser multiplataforma (macOS y Windows), con una UI moderna y sin depender de toolkits gráficos nativos. Decidimos que el ejecutable levante un servidor HTTP en loopback, elija un puerto libre y abra el navegador por defecto del usuario; la UI es una SPA servida por ese mismo servidor.

## Considered Options

- **GUI nativa en Python (Qt/PySide)**: descartada por peso del binario (~100 MB) y costo de estilización.
- **Tauri o PyWebView**: descartadas por requerir toolchain adicional (Rust) o por sumar un webview propio sin ventaja frente al navegador ya instalado.
- **SwiftUI/WinUI**: descartadas por no ser multiplataforma.

## Consequences

- No hay selector de carpetas en la página: `Destination` se elige con el diálogo nativo que abre el servidor (ADR-0012).
- La app sigue viva si el usuario cierra la pestaña y no tiene ventana propia ni ícono de bandeja. Para que no quede un proceso invisible indefinidamente, el MVP incluye un botón "Cerrar aplicación" y un `Idle Shutdown`: la app se cierra sola unos 15 segundos después de que se cierre la última pestaña, con la `Queue` vacía (si no se ha conectado ninguna pestaña desde el arranque, espera 60 segundos). El plazo es corto porque actualizar la app exige que la versión anterior ya no esté corriendo: macOS no deja reemplazar un `.app` en uso y, mientras siga viva, `Single Instance` reutilizaría la instancia vieja. Una descarga en curso retrasa el cierre hasta que termine; recargar la pestaña no lo dispara, porque la nueva conexión llega antes del plazo. El ícono de bandeja queda como mejora posterior.
- En macOS empaquetado el ejecutable del `.app` no es el servidor: lanza el servidor como proceso hijo desacoplado (sesión nueva, fuera de LaunchServices) y termina enseguida. LaunchServices permite una sola instancia por bundle y, al reabrir, pide al proceso existente que se active; un servidor Python no es una app Cocoa y no responde, así que Finder mostraba "La aplicación YouTube Downloader ya no está abierta." y `Single Instance` nunca se ejecutaba. Con el lanzador de corta vida, cada doble clic pasa por `Single Instance` y abre una pestaña en la instancia existente. Costo: no hay icono en el Dock mientras la app corre.
- Descartado: una app Cocoa con PyObjC (icono en el Dock y "Salir" desde el Dock), por coste de dependencia y riesgo de empaquetado frente a lo que aporta.
- El servidor solo escucha en `127.0.0.1`.
