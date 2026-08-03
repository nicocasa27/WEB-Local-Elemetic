## BD y migraciones

Este proyecto usa 2 bases de datos:

- `mes` (Postgres): datos operativos de `produccion` y `catalogos`.
- `default` (SQLite): apps no ruteadas (por ejemplo `auth`, `admin`, `sessions`).

### Reglas de ruteo

- Todo lo que pertenezca a `produccion` o `catalogos` se lee/escribe en `mes`.
- El resto se mantiene en `default`.

### Migraciones

- `produccion` y `catalogos` solo deben migrarse en `mes`.
- Las migraciones de apps estándar (auth, sesiones, admin) siguen en `default`.

### Señales de problema típicas

- Si aparece “tabla no existe” para modelos de `produccion`/`catalogos`, normalmente es porque se migró en `default` en lugar de `mes`.
- Si hay errores de conexión a Postgres, revisar variables de entorno `MES_DB_*`.
