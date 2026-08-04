# Plantillas que ya no renderiza nadie

Las tres estaban en su carpeta de plantillas como si estuvieran vivas, y no
lo estaban. Eso engaña: quien busca dónde se dibuja la pantalla de control de
Herrería abre `herreria_control.html` y edita un archivo que el servidor no
mira nunca.

- **`herreria_control.html`** (282 líneas) — la vista `herreria_control`
  renderiza `catalogos/herreria_list.html`. Esta es una versión anterior.
- **`herreria_home.html`** (40 líneas) — nadie la nombra.
- **`viga_global.html`** (83 líneas) — la vista `viga_global` sólo hace
  `redirect("produccion:solo_lectura_produccion")`.

No se borran: pueden servir de referencia y no estorban aquí. Si alguna hace
falta, se devuelve a su carpeta y ya está.
