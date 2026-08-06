# Lecciones

Cada corrección del usuario deja una regla aquí. No la anécdota: **la regla que
evita repetirlo**. Se repasa al empezar la sesión.

---

## Herramientas

### No abrir Chrome salvo que se pida

**Qué pasó:** verifiqué media pantalla de login abriendo el navegador, midiendo
elementos y sacando capturas, cuando lo mismo se comprobaba leyendo el HTML
servido y con una prueba.

**Por qué importa:** es lento, ensucia el contexto y casi nunca dice nada que no
dijera un test. Y cuando el navegador es la única forma de verlo, casi siempre
significa que falta una prueba.

**La regla:** verificar con `pytest`, con `curl` o leyendo el HTML. El navegador,
sólo cuando se pida explícitamente o cuando lo que se comprueba **sea** el
render y no haya otra forma. En ese caso, una pasada, no diez.

---

## Django

### `{# … #}` es de una sola línea

**Qué pasó:** un comentario de dos líneas con esa sintaxis, dentro del `<head>`.
Django lo imprime tal cual, el navegador ve texto suelto, da la cabecera por
cerrada y **mete las hojas de estilo dentro del cuerpo**. La página se descoloca
entera y el síntoma —«la tarjeta no está centrada»— no se parece en nada a la
causa.

**La regla:** para varias líneas, `{% comment %}`. Lo vigila
`tests/test_diseno.py::TestLosComentariosNoSeVenEnPantalla`.

### Un campo de fecha necesita el formato ISO

**Qué pasó:** el sistema está en `es-mx`, así que Django pintaba
`value="06/08/2026"` en un `<input type="date">`, que sólo entiende
`2026-08-06`. El navegador tiraba el valor. Estaba en los catorce sitios donde
se declaró el widget a mano, o sea en todas las fechas del sistema.

**La regla:** `core.campos.CampoDeFecha`, nunca `forms.DateInput` a mano. Lo
vigila `tests/test_campos_de_fecha.py`.

### Las casillas fuera del `<form>` necesitan `form="..."`

**Qué pasó:** los permisos de un usuario vivían en un segundo `<form>` sin
botón. Al guardar no llegaba ninguno y se le quitaban **todos** los permisos sin
decir nada. El síntoma aparecía al día siguiente.

**La regla:** si un campo se pinta fuera del formulario al que pertenece, lleva
`attrs={"form": "<id-del-form>"}`, y una prueba que lo compruebe.

---

## Guardias

### Un guardia que vigila tres puertas de siete es peor que no tenerlo

**Qué pasó:** la prueba de comentarios abiertos sólo miraba `produccion`,
`catalogos` y `nucleo`. No miraba `templates/`, que es donde está la pantalla de
entrar. Daba sensación de estar cubierto sin estarlo.

**La regla:** un guardia estructural recorre **todo** el árbol y afirma cuántas
carpetas encontró. Nada de listas escritas a mano que envejecen con cada app
nueva.

---

## Verificación

### Reiniciar el servidor después de tocar código

**Qué pasó:** dejé el servidor corriendo con `--noreload`, seguí cambiando
plantillas y vistas durante horas, y el usuario probó la versión de antes. Dos
veces.

**La regla:** el servidor de pruebas se levanta **sin** `--noreload`. Y antes de
pedir que alguien mire algo, comprobar que lo servido es lo escrito.

### Un dato de prueba inventado prueba algo que no pasa

**Qué pasó:** mandé `grupos: ""` en un POST de prueba y falló la validación. Una
casilla sin marcar no manda cadena vacía: **no manda nada**. El fallo era del
test, no del código.

**La regla:** cuando una prueba falle por validación, comprobar primero que lo
enviado es lo que enviaría un navegador de verdad.
