# Lecciones

Cada corrección del usuario deja una regla aquí. No la anécdota: **la regla que
evita repetirlo**. Se repasa al empezar la sesión.

---

## Cómo contestar

### Pedir algo: qué es, dónde está, para qué

**Qué pasó:** pedí «la contraseña de la base». ¿De qué base? ¿De dónde se saca?

**La regla:** al pedir un dato, tres cosas en la misma frase: **qué** es
exactamente, **dónde** se encuentra —ruta de clics o URL, no «en el panel»— y
**para qué** hace falta. Si puede no saberlo, decir también cómo obtenerlo.

### Decir si algo quedó hecho o pendiente

**Qué pasó:** «encontré este error, pero ya lo arreglé» sin que quede claro si
está resuelto, a medias o pendiente.

**La regla:** cada cosa que se menciona lleva su estado sin ambigüedad: hecho /
pendiente / bloqueado por X. Si hay varias, una tabla. Nunca dejar al lector
deduciendo en qué quedó algo.

### Corto

**Qué pasó:** «tienes que preguntar más conciso, dices mucha mamada».

**La regla:** el resultado primero, en una línea. Las preguntas, una línea cada
una. Explicar el porqué **sólo** si cambia una decisión, y en una frase.

Nada de recapitular lo hecho, repetir lo que ya está en el commit, ni justificar
cada elección. Si hace falta el detalle, está en `tasks/todo.md` y en el mensaje
del commit — ahí es donde se busca, no en el chat.

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

### Dos alias a la misma base son dos transacciones, no una

**Qué pasó:** para unificar las dos bases sin tocar las 846 llamadas
`.using("mes")`, dejé los dos alias apuntando al mismo PostgreSQL. Django abre
**una conexión por alias**, así que lo escrito por `default` no lo veía `mes` y
las claves foráneas reventaban: 26 fallos y 8 errores en la suite.

**Por qué importa:** en pruebas se ve. En producción no: `transaction.atomic(using="mes")`
simplemente dejaría de cubrir lo que se escribe por el otro alias, y eso no
falla, sólo deja los datos a medias de vez en cuando.

**La regla:** un alias por base física. Si dos alias apuntan al mismo sitio, no
hay atomicidad entre ellos por mucho que la base sea una. Cambiar de base y
retirar el alias son **el mismo movimiento**.

### El nombre del esquema escrito dentro del SQL ignora el `search_path`

**Qué pasó:** `esquema_heredado.sql` venía de un `pg_dump` con `public.` en cada
tabla, secuencia e índice. Con un esquema por ERP, las tablas heredadas
aterrizaban en `public` y Django no las encontraba.

**La regla:** un volcado que vaya a cargarse en un esquema distinto del de
origen se limpia de nombres de esquema y decide la conexión. Y el `pg_dump` es
el de la versión del **destino**, no el que esté en el PATH.

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
