---
status: accepted
---

# SQLite es la fuente de verdad de la cola y el historial

Un estado en memoria perdía los jobs al cerrar la app y no daba historial. Decidimos persistir batches y jobs en SQLite dentro del directorio de datos (`~/.youtube-downloader/db.sqlite3`), en modo WAL.

## Consequences

- Los jobs en curso al cerrar quedan como `interrupted` y se ofrecen para reintento; no se reanudan solos.
- Hay que versionar el esquema con migraciones simples.
- SQLite serializa escrituras; el runner debe agrupar las actualizaciones de progreso para no saturar la base.
