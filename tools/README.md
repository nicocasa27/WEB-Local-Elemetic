# Herramientas de diagnóstico

Scripts de un solo uso que se conservan porque encontraron defectos reales
y sirven para comprobar que no vuelven a aparecer.

## `detectar_bloques_sobreindentados.py`

Busca cuerpos de `if`/`else`/`for`/`with`/`except` indentados más de cuatro
espacios respecto a la sentencia que los encabeza.

Ese es el rastro que dejó `cleanup.py` (eliminado en el commit de limpieza)
al borrar líneas de en medio de bloques anidados: el cuerpo conserva la
indentación profunda, pero el `else:` queda un nivel más afuera y pasa a
colgar de otra condición. Python no se queja, porque la indentación sigue
siendo consistente dentro del bloque.

Encontró seis casos, entre ellos el que hacía imposible registrar un paro
de máquina y el que impedía eliminar piezas de los tres catálogos.

```
python3 tools/detectar_bloques_sobreindentados.py catalogos/views.py produccion/views.py
```

Salida esperada hoy: cero hallazgos.

## `detectar_else_con_nombres_indefinidos.py`

Complementario del anterior. Busca ramas `else` que leen nombres asignados
únicamente dentro del `body` del mismo `if`, es decir, ramas que sólo pueden
terminar en `NameError`.

Tiene falsos positivos cuando el nombre se asigna en las dos ramas; hay que
revisar cada hallazgo a mano.

```
python3 tools/detectar_else_con_nombres_indefinidos.py catalogos/views.py
```

Para la detección continua de nombres indefinidos, la herramienta buena es
`ruff check --select F82`, que ya corre en cada commit vía `pre-commit`.
