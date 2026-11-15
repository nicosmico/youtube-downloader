---
status: accepted
---

# Solo contenido público, sin cookies ni cuentas

El soporte de autenticación y de `--cookies-from-browser` es frágil entre macOS y Windows, y el producto no lo necesita. Decidimos que la app solo descargue `Contenido público` y que falle con un mensaje claro cuando YouTube exija inicio de sesión o verificación.

## Consequences

- Videos privados, con restricción de edad o con muro de login quedan fuera de alcance.
- No hay superficie de riesgo asociada a credenciales del usuario.
