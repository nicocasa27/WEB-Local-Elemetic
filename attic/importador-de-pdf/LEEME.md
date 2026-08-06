# El importador de vigas desde PDF

Seiscientas dieciocho líneas que vivían en `produccion/views.py` **sin ninguna
ruta en `urls.py`**. No se podía abrir desde ningún sitio del sistema, ni
escribiendo la dirección a mano: no existía. Su plantilla enlazaba a
`{% url 'produccion:viga_import' %}`, que hoy ni siquiera resuelve.

- **`viga_import.py`** — la vista y su analizador de PDF, más los dos ayudantes
  (`_guess_mapping`, `_normalize_row`) que se quedaron huérfanos al sacarla,
  porque eran los únicos que los llamaban.
- **`viga_import.html`** — su plantilla.

Estorbaba de dos maneras. Quien abría `views.py` buscando cómo se dan de alta
las vigas se encontraba esto primero y creía haber dado con el camino bueno. Y
cada búsqueda, cada revisión y cada refactor del archivo tenía que pasar por
encima de seiscientas líneas que no hacen nada.

**No se borra.** El analizador conoce el formato de los PDF de obra de este
taller, y ese conocimiento no está escrito en ningún otro sitio; cuando se monte
el inventario de materia prima puede servir para leer certificados de material.

**El modelo `catalogos.PdfExtractionTemplate` se queda donde estaba.** Aquí sólo
se aparca código: esa tabla tiene datos y las tablas no se tocan.

Para revivirlo: devolver el bloque a `produccion/views.py`, devolver la
plantilla a `produccion/templates/produccion/`, añadir la ruta en
`produccion/urls.py`, y volver a importar `PdfExtractionTemplate`.
