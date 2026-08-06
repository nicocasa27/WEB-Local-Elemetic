# Cómo se trabaja en este proyecto

Instrucciones permanentes. Se leen al empezar cada sesión.

---

## 1. Planificar antes de construir

- **Modo de planificación para cualquier tarea no trivial**: 3 o más pasos, o
  cualquier decisión de arquitectura.
- **Si algo sale mal, parar y replanificar.** No seguir empujando el mismo
  enfoque a ver si cede.
- Planificar también **los pasos de verificación**, no sólo los de construir.
- Escribir la especificación por adelantado. La ambigüedad se paga después.

## 2. Subagentes

- Usarlos con generosidad para no ensuciar el contexto principal.
- Descargar en ellos la investigación, la exploración y el análisis paralelo.
- Un asunto por subagente. Uno que hace tres cosas no hace bien ninguna.
- Para un problema difícil, más cómputo repartido en subagentes.

## 3. Ciclo de mejora

- **Después de cualquier corrección del usuario, escribir el patrón en
  `tasks/lessons.md`.** No la anécdota: la regla que evita repetirlo.
- Repasar `tasks/lessons.md` al empezar la sesión.

## 4. Verificar antes de dar algo por hecho

- **Nunca marcar una tarea como terminada sin demostrar que funciona.**
- Cuando venga al caso, comparar el comportamiento con el de `main`.
- La pregunta antes de entregar: *¿esto lo aprobaría un ingeniero senior?*
- Correr las pruebas, mirar los registros, enseñar el resultado.

## 5. Elegancia, con medida

- En un cambio no trivial, pararse a preguntar: *¿hay una forma más elegante?*
- Si un arreglo sale con prisa: rehacerlo sabiendo lo que ya se sabe.
- **En un arreglo obvio, saltarse esto.** No sobrediseñar.
- Cuestionar el propio trabajo antes de presentarlo.

## 6. Errores: arreglarlos, no consultarlos

- Ante un informe de error: **arreglarlo**. Sin pedir que lleven de la mano.
- Señalar el registro, el error o la prueba que falla, y resolverlo.
- Cero cambio de contexto para quien lo reportó.

---

## Herramientas

- **Chrome sólo cuando se pida explícitamente.** No abrirlo para comprobar
  cosas que se comprueban con una prueba, con `curl` o leyendo el HTML. Es
  lento, ensucia el contexto y casi nunca dice nada que no dijera un test.
- Preferir las herramientas dedicadas de archivos y búsqueda antes que la
  consola.

## Gestión de tareas

1. **Planificar**: el plan va en `tasks/todo.md`, con casillas.
2. **Verificar el plan** antes de empezar.
3. **Marcar** cada punto al terminarlo.
4. **Explicar** cada paso con un resumen corto.
5. **Documentar**: sección de revisión al final de `tasks/todo.md`.
6. **Recoger lecciones** en `tasks/lessons.md` después de cada corrección.

## Principios

- **Simplicidad primero.** Que cada cambio sea el más simple que resuelva el
  problema, y que toque el mínimo de código.
- **Sin pereza.** Buscar la causa raíz. Nada de parches temporales.
- **Impacto mínimo.** Tocar sólo lo necesario. No introducir errores nuevos
  por el camino.

---

## Lo que este proyecto en concreto no perdona

Estas no son preferencias, son restricciones del taller. Están explicadas en
`DESPLIEGUE.md` y en `README.md`.

- **No se borran datos.** Añadir tablas y columnas, sí. Migraciones sólo
  `AddField`, `CreateModel`, `AddIndex`, `AddConstraint`. Regla operativa: *un
  `git revert` del código tiene que dejar el sistema en pie sin tocar la base.*
- **El repositorio es privado y sigue siéndolo.** Lleva contraseñas en claro
  porque el taller lo pidió así.
- **El taller no tiene internet.** Nada de CDN. Todo servido desde disco.
- **Derivar, no copiar.** Los totales se calculan; un total guardado se queda
  viejo.
- **`transaction.atomic()` siempre con `using=`.** Sobre dos bases, sin eso no
  hay atomicidad.
- **`{# … #}` es de una sola línea.** En varias, Django lo imprime en la
  página. Para varias, `{% comment %}`.
- Las pruebas se corren con `pytest`. Hay guardias estructurales que valen más
  que un caso concreto: mantenerlos y ampliarlos cuando se escape algo.
