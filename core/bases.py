"""Por qué alias se escribe el negocio.

Todo el proyecto usa `BASE`. Nadie escribe `"mes"` a mano, y hay una prueba que
lo vigila (`tests/test_guardias.py`).

**Por qué no puede ser una cadena fija.** Django abre una conexión por alias. Si
`default` y `mes` apuntan al mismo PostgreSQL —que es lo que pasa al unificar
las dos bases— son dos transacciones distintas contra la misma base: lo que
escribe una no lo ve la otra, y `transaction.atomic(using="mes")` deja de cubrir
lo que se escribe por `default`. Se comprobó: la suite revienta con
`ForeignKeyViolation` en veintiséis pruebas de almacén.

Y dejarlo en `"default"` mientras haya dos bases es peor todavía: sería abrir la
transacción sobre SQLite mientras se escribe en PostgreSQL, la «atomicidad
falsa» que este proyecto ya arregló una vez y que vigila
`test_las_transacciones_indican_siempre_la_base`.

O sea que **no se puede migrar a medias**: retirar el alias y cambiar de base
son el mismo movimiento. Esto es lo que lo convierte en un interruptor
(`MES_UNA_SOLA_BASE`) en vez de en trescientas ediciones a mano.
"""

from django.conf import settings

#: El alias de la base del negocio. `"mes"` con dos bases, `"default"` con una.
#:
#: Se resuelve al importar. Eso está bien: la configuración de bases de datos no
#: cambia mientras el proceso corre, y resolverlo en cada llamada costaría un
#: acceso a los ajustes en cada consulta del sistema.
BASE = getattr(settings, "MES_DB_ALIAS", "mes")
