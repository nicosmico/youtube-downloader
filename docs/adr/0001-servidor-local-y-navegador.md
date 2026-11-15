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

- No hay selector nativo de carpetas: `Destination` es fijo.
- La app sigue viva si el usuario cierra la pestaña y no tiene ventana propia ni ícono de bandeja. Para que no quede un proceso invisible indefinidamente, el MVP incluye un botón "Cerrar aplicación" y un `Idle Shutdown`: la app se cierra sola tras 10 minutos sin pestañas conectadas y con la `Queue` vacía. El ícono de bandeja queda como mejora posterior.
- El servidor solo escucha en `127.0.0.1`.
