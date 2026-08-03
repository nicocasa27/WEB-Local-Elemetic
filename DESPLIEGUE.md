# Despliegue

## Cómo arranca hoy

El servidor del taller ejecuta `INICIAR_SERVIDOR.bat`, que hace:

```bat
cd /d "C:\Users\Usuario\Documents\trae_projects\DJANGO WEB"
set MES_DB_HOST=127.0.0.1
.venv\Scripts\python.exe manage.py runserver 0.0.0.0:8501
```

Sin `DJANGO_ENV`, eso carga la configuración de **desarrollo**, que es
exactamente el comportamiento que había antes de separar la configuración por
entornos. Nada se rompe por no hacer nada.

Lo que sí conviene es pasar a producción, porque en desarrollo:

- `DEBUG` está activo, así que cualquier error muestra una traza con la
  configuración dentro, **incluida la contraseña de PostgreSQL**;
- la clave de firma de sesiones es pública (está en el repositorio).

## Pasar el servidor a producción

Todo esto se hace **en la máquina del taller**. Conviene hacerlo fuera de
horario y con un respaldo reciente.

### 1. Respaldar

```bat
pg_dump -Fc -h 127.0.0.1 -U postgres mes_vigas -f respaldo_mes_vigas.dump
copy db.sqlite3 db.sqlite3.respaldo
```

Comprobar que el respaldo restaura en una base de prueba antes de seguir.

### 2. Generar la clave de firma

```bat
.venv\Scripts\python.exe -c "from django.core.management.utils import get_random_secret_key as g; print(g())"
```

Guardar el resultado: es el valor de `DJANGO_SECRET_KEY`.

> Cambiar esta clave **cierra todas las sesiones abiertas**. Todo el mundo
> tendrá que volver a iniciar sesión. Por eso conviene hacerlo al final de la
> jornada y avisar antes.

### 3. Crear el archivo `.env`

Copiar `.env.example` a `.env` en la carpeta `DJANGO WEB` y rellenarlo. Como
mínimo `DJANGO_ENV=prod`, `DJANGO_SECRET_KEY` y `MES_DB_PASSWORD`.

`.env` no se versiona. No se sube al repositorio ni se manda por correo.

### 4. Recoger los archivos estáticos

Con `DEBUG` apagado Django ya no sirve el CSS ni el JavaScript por su cuenta;
hay que juntarlos en `STATIC_ROOT`:

```bat
.venv\Scripts\python.exe manage.py collectstatic --noinput
```

Hay que repetirlo después de cada actualización que toque archivos estáticos.

### 5. Actualizar el .bat de arranque

```bat
@echo off
title Servidor Web Taller Elemetic - Django
cd /d "C:\Users\Usuario\Documents\trae_projects\DJANGO WEB"

set DJANGO_ENV=prod
set MES_DB_HOST=127.0.0.1
for /f "usebackq tokens=1,* delims==" %%a in (".env") do (
    if not "%%a"=="" if not "%%a:~0,1%"=="#" set "%%a=%%b"
)

.venv\Scripts\python.exe manage.py runserver 0.0.0.0:8501
pause
```

Si el bucle de lectura del `.env` da problemas en esa versión de Windows, la
alternativa es poner los `set` a mano en el `.bat` y proteger el archivo.

### 6. Comprobar

```bat
.venv\Scripts\python.exe manage.py check --deploy
```

Con la configuración de producción quedan seis avisos, todos esperados y
explicados en la sección siguiente. Si aparece `ImproperlyConfigured`, falta
una variable: el mensaje dice cuál.

Después, con el servidor arrancado: entrar, abrir el tablero, abrir un plano
en PDF y registrar un avance.

## Avisos de `check --deploy` que quedan y por qué

| Aviso | Motivo |
|---|---|
| `W004` HSTS | Requiere HTTPS. Se activa solo al poner `DJANGO_HTTPS=1`. |
| `W008` `SECURE_SSL_REDIRECT` | Igual: el taller sirve por HTTP en la red local. Activarlo sin certificado dejaría a todos fuera. |
| `W012` `SESSION_COOKIE_SECURE` | Igual. |
| `W016` `CSRF_COOKIE_SECURE` | Igual. |
| `W009` clave corta | Desaparece al poner una clave generada de verdad. |
| `W019` `X_FRAME_OPTIONS` | Está en `SAMEORIGIN` a propósito: las pantallas de Corta abren contenido propio dentro de un `iframe`. Ponerlo en `DENY` rompería esos modales. |

Los cuatro primeros se cierran de golpe el día que se ponga un proxy con TLS
delante y se defina `DJANGO_HTTPS=1`.

## Archivos subidos

Planos, DXF y comprobantes de envío se sirven por `mes_vigas_web/media_views.py`,
que **exige sesión iniciada**. Antes sólo se servían con `DEBUG` activo (o sea,
dejaban de funcionar en producción) y sin comprobar nada: un acuse de entrega
firmado era accesible para quien acertara la dirección.

## Tarea programada: consolidar los cierres

Cuando una orden llega a su objetivo de piezas queda en «Terminado (bloqueo
pend.)» unos minutos, para poder deshacer un error de dedo. Pasado ese plazo el
cierre debe volverse firme.

Hasta ahora eso sólo ocurría **al abrir la pantalla de control**, así que un
cierre que vencía un viernes a las 17:05 seguía pendiente el lunes por la
mañana, y figuraba como tal en todos los informes.

Hay que programar este comando cada minuto:

```bat
.venv\Scripts\python.exe manage.py consolidar_cierres
```

En Windows, con el Programador de tareas: tarea nueva, repetir cada 1 minuto
indefinidamente, acción «iniciar programa» apuntando al `python.exe` del
entorno virtual, con `manage.py consolidar_cierres` como argumentos y la
carpeta `DJANGO WEB` como directorio de inicio. Conviene marcar «no iniciar una
nueva instancia si ya se está ejecutando».

Para ver qué haría sin tocar nada:

```bat
.venv\Scripts\python.exe manage.py consolidar_cierres --simular
```

El comando no imprime nada cuando no hay trabajo, para no llenar el registro.

Mientras la tarea no esté configurada, la pantalla de control sigue
consolidando los cierres al cargarse, igual que antes: no se rompe nada por
no hacerlo, sólo se mantiene el retraso.

## Registro de actividad

Los registros van a `logs/`, con rotación a los 10 MB y cinco archivos de
histórico:

- `logs/mes.log` — todo lo que llega a nivel INFO o superior.
- `logs/errores.log` — sólo errores y excepciones.

Si algo falla y el usuario no sabe explicar qué, `logs/errores.log` es el
primer sitio donde mirar.

## Pendiente: unificar las dos bases de datos

Hoy la autenticación vive en `db.sqlite3` y los datos de negocio en
PostgreSQL. Esa separación no responde a ninguna decisión de diseño (es lo que
deja `startproject`) y causa tres problemas:

- Django no admite claves foráneas entre bases distintas, así que ningún
  registro puede apuntar a quien lo hizo. La identidad se guarda como texto
  libre en catorce campos; cambiar el nombre de un usuario deja huérfano todo
  su historial.
- Hay que respaldar dos bases y cuadrarlas: un volcado de PostgreSQL sin su
  SQLite correspondiente no restaura nada.
- SQLite admite un solo escritor a la vez, de modo que las sesiones de todo el
  taller pasan por un cuello de botella.

Está preparado el comando `migrar_auth_a_postgres`, que copia usuarios, grupos
y permisos con las contraseñas ya cifradas (nadie tiene que cambiar la suya) y
comprueba después que el censo coincide.

**El cambio no se ha ejecutado**, y conviene saber por qué antes de intentarlo.

### El obstáculo que hay que resolver primero

Al probarlo sobre una copia apareció una inconsistencia que no se veía desde
fuera: la tabla `django_migrations` de PostgreSQL tiene **registradas como
aplicadas** las migraciones de `auth`, `contenttypes`, `sessions` y `admin`,
pero **esas tablas no existen** en esa base.

Es el comportamiento normal de Django: cuando el router responde que una
aplicación no debe migrarse a cierta base, Django no crea nada pero sí anota
la migración como aplicada. Con los años, el registro quedó diciendo una cosa
y la base conteniendo otra.

La consecuencia práctica es que permitir sin más que `auth` se cree en
PostgreSQL no crea nada: Django cree que ya está hecho. Y desmarcar esas
migraciones arrastra a las de `catalogos`, que dependen de ellas, con lo que
el planificador intenta recrear tablas que ya existen.

Se probó en una copia, se rompió el registro de migraciones y se restauró
desde el respaldo. Esa es exactamente la clase de sorpresa que hay que
encontrar en una copia y no en el servidor un sábado por la noche.

### Cómo abordarlo

Hace falta una sesión dedicada, con el respaldo recién hecho y sin prisa:

1. Reconstruir el registro de migraciones de PostgreSQL para que refleje la
   realidad, en lugar de pelearse con él a base de `--fake`.
2. Crear las tablas de autenticación en PostgreSQL.
3. Copiar los datos con `migrar_auth_a_postgres` y verificar el censo.
4. Decidir el destino: o `default` pasa a apuntar a PostgreSQL conservando el
   alias `mes`, o se elimina el alias y se sustituyen las ciento cincuenta
   llamadas `.using("mes")`. Lo segundo deja el sistema más limpio y es lo que
   conviene de cara a la unificación del núcleo, pero es un cambio amplio que
   necesita la suite de pruebas en verde antes y después.
5. Reiniciar y comprobar que todo el mundo puede entrar.

La vuelta atrás es devolver la configuración anterior: el `db.sqlite3` queda
intacto durante todo el proceso.

## El núcleo unificado: cómo se pone en marcha

Las cuatro líneas —vigas, herrería, corte láser y robótica— son hoy el mismo
motor copiado cuatro veces. El paquete `nucleo` es el destino común. **Está
instalado pero apagado**: sin encender ninguna bandera no cambia absolutamente
nada de lo que ve el taller.

El cambio se hace **una línea cada vez**, y cada paso se deshace solo.

### Los tres estados de una línea

Se controlan con una variable de entorno por línea:

| Valor | Qué pasa |
|---|---|
| *(sin poner)* | Apagada. El núcleo existe y nadie lo usa. **Así está hoy.** |
| `doble` | Las vistas escriben donde siempre y además se refleja en el núcleo. La verdad sigue siendo la tabla heredada. |
| `corte` | El núcleo pasa a ser la fuente de verdad. |

```bat
set MES_NUCLEO_ROBOTICA=doble
set MES_NUCLEO_CORTA=doble
set MES_NUCLEO_HERRERIA=doble
set MES_NUCLEO_VIGAS=doble
```

Una errata en el valor se trata como apagado, a propósito: una variable mal
escrita no debe encender una escritura nueva sobre la base de producción.

### Puesta en marcha, con la base parada o fuera de horario

```bat
.venv\Scripts\python.exe manage.py migrate nucleo --database=mes
.venv\Scripts\python.exe manage.py sembrar_nucleo --simular
.venv\Scripts\python.exe manage.py sembrar_nucleo
.venv\Scripts\python.exe manage.py backfill_nucleo --simular
.venv\Scripts\python.exe manage.py backfill_nucleo
.venv\Scripts\python.exe manage.py verificar_backfill
```

`sembrar_nucleo` **se niega a continuar** si encuentra en la base un valor de
estado que no sabe representar. No es un estorbo: significa que hay datos cuya
forma no conocíamos, y seguir en ese momento sería perder esas órdenes.

`backfill_nucleo` sólo lee de las tablas heredadas. Se puede repetir las veces
que haga falta sin duplicar nada.

`verificar_backfill` compara censo, kilos, reparto por etapas y la suma del
historial contra los contadores. **Si no sale limpio, no se sigue.**

### El rodaje

Con la línea en `doble`, programar una vez al día:

```bat
.venv\Scripts\python.exe manage.py reconciliar_nucleo
```

Compara fila a fila y anota lo que no coincida. Para ver cómo va:

```bat
.venv\Scripts\python.exe manage.py reconciliar_nucleo --resumen
```

**Una línea no se corta hasta que lleve siete días seguidos sin ninguna
diferencia.** Ese control es lo que convierte la migración en algo aburrido:
cuando llega el día del corte ya se sabe desde hace una semana que las dos
mitades dicen lo mismo.

El reflejo va enganchado con señales de Django, así que cubre cualquier camino
que guarde por el ORM. Lo que **no** cubre son las nueve escrituras en bloque
(`.filter(...).update(...)`) que hay en el código: de ésas se ocupa la
reconciliación, que además sabe repararlas con `--corregir`.

### El corte, y cómo se deshace

Orden por riesgo creciente: **robótica → corte láser → herrería → vigas**.
Robótica va primera porque ni siquiera tiene máquina de estados: es la que
menos tiene que perder.

```bat
set MES_NUCLEO_ROBOTICA=corte
```

Volver atrás es poner `doble` otra vez y reiniciar. No hay que restaurar nada:
las tablas heredadas siguen ahí y siguen actualizadas. **Ninguna tabla vieja se
borra jamás**; cuando dejen de usarse se renombran y quedan en sólo lectura.

### La invariante de contadores

Se puede guardar «soldadas 0, pintadas 0, terminadas 50», y esas cincuenta
piezas salen en los informes sin haber pasado por ninguna etapa. El servicio
del núcleo ya no lo permite. Para llevarlo también a la base:

```bat
.venv\Scripts\python.exe manage.py endurecer_invariantes
```

Eso sólo informa. En la copia del taller hay **tres órdenes** que la incumplen:
H-00031, L-00014 y H-00020. Hay que corregirlas **antes** de endurecer nada, y
con un evento de ajuste con su motivo, no con un `UPDATE`: la corrección tiene
que quedar en el historial como cualquier otro movimiento.

Sólo cuando no quede ninguna:

```bat
.venv\Scripts\python.exe manage.py endurecer_invariantes --aplicar
.venv\Scripts\python.exe manage.py endurecer_invariantes --validar
```

> **Por qué en ese orden.** `--aplicar` crea la regla como `NOT VALID`, que
> tolera que las filas malas *existan* pero **no que se modifiquen**. Aplicarla
> antes de corregirlas deja esas órdenes congeladas: no se pueden actualizar, y
> durante la escritura doble el reflejo falla en silencio, porque está pensado
> para no interrumpir al operador. Se comprobó en la copia: L-00014 dejó de
> poder actualizarse. Por eso `--aplicar` se niega si quedan órdenes malas, y
> hay `--quitar` para retirar la regla si algo se atasca.

### Lo que hay que decidir antes de cortar herrería

- **Corta de una pieza**: ¿pasa por almacén o se entrega directa? Ya es una
  casilla (`LineaNegocio.usa_almacen`), pero la respuesta es de negocio.
- **Reversión de cierre**: ¿sólo quien cerró, o también un supervisor? Hoy el
  servicio exige motivo siempre y no restringe quién; para restringirlo basta
  poner el grupo en la transición correspondiente, sin tocar código.

### Editar el proceso sin programar

Etapas, transiciones y motivos están en el administrador de Django, en
«Núcleo». Añadir un granallado, exigir un grupo para cerrar o marcar que una
transición se bloquee con la máquina parada es editar una fila.

Los eventos son de sólo lectura y no se pueden borrar. Es deliberado: un
registro que se puede editar deja de ser un registro, y con él se va la única
razón para fiarse de los números.

## Inventario de materia prima

Hoy el sistema sabe qué se produce pero no con qué. Lo más parecido a un
catálogo de material es `LaserMaterialPlaca`: 113 placas con su geometría y su
peso, sin costo, sin proveedor y sin existencias. Cuando un cliente reclama, no
hay forma de saber de qué colada salió la pieza.

El módulo `inventario` añade lo que faltaba. **Está instalado y vacío**: no
cambia nada hasta que se cargue el conteo inicial.

### Puesta en marcha

```bat
.venv\Scripts\python.exe manage.py migrate inventario --database=mes
.venv\Scripts\python.exe manage.py sembrar_inventario
```

Eso crea el almacén, los motivos y trae las 113 placas ya catalogadas, con su
peso y su densidad. **Todo queda en existencia cero, a propósito**: un almacén
que arranca con cifras inventadas no vuelve a cuadrar nunca, y encima se cree.

### El conteo físico

```bat
.venv\Scripts\python.exe manage.py inventario_fisico --plantilla conteo.csv
```

Sale una hoja con una fila por material. Se baja al almacén, se cuenta y se
rellena la columna `contado`. Las filas en blanco no se tocan, así que se puede
contar por partes.

**Las columnas `lote` y `colada` importan más de lo que parecen**: son lo que
después permite responder de qué colada salió una pieza. Si no se saben, se
dejan vacías y el material entra en un lote de inventario inicial que deja
constancia explícita de que llegó sin certificado.

```bat
.venv\Scripts\python.exe manage.py inventario_fisico --cargar conteo.csv --simular
.venv\Scripts\python.exe manage.py inventario_fisico --cargar conteo.csv
```

La primera carga es el inventario inicial. **Las siguientes registran la
diferencia** entre lo contado y lo que el sistema creía, con motivo «conteo
físico». Esa diferencia es la única medida real de si el inventario se está
llevando bien, y por eso queda escrita en vez de sustituirse en silencio.

### Las dos preguntas que ahora sí tienen respuesta

```bat
.venv\Scripts\python.exe manage.py trazar --colada H-48213
.venv\Scripts\python.exe manage.py trazar --orden L-00014
```

La primera es la que llega cuando la acería avisa de un lote defectuoso o un
cliente reclama: dónde está esa colada. La segunda es la inversa: de qué está
hecha una orden, con qué proveedor y si hay certificado. También da el costo de
material de la orden.

### Vigilancia diaria

```bat
.venv\Scripts\python.exe manage.py verificar_inventario
```

Las existencias son una caché; el número bueno es la suma de los movimientos.
Si se separan, alguien escribió por un camino que no pasa por el servicio.
`--corregir` las reconstruye desde el historial. Informa además de qué está por
debajo de su mínimo y de cuánto dinero hay parado en el almacén, valuado lote a
lote y no por promedio.

### Qué hace y qué no

- El material **sale por antigüedad de lote**: primero lo que entró antes. Eso
  es lo que hace que el costo de una orden sea el de lo que de verdad se metió
  en ella.
- **No se puede sacar lo que no hay.** Lo impide el servicio y lo impide la
  base, así que no hay ningún camino —ni un `update` en bloque— capaz de dejar
  el almacén debiendo material.
- **La lista de materiales propone, no descuenta.** Una lista incorrecta que
  descuenta sola vacía el inventario en una semana y nadie se entera hasta que
  hay que comprar. Se automatiza cuando `comparar_consumo` demuestre que lo
  previsto y lo real coinciden.
- **La merma es un tipo propio, no un ajuste.** La merma es una pérdida que se
  puede medir y reducir; el ajuste es que la cuenta estaba mal. Mezclarlas hace
  imposible saber cuánto se está tirando.

### Lo que decide si esto sirve, y no es técnico

**Sin un conteo físico inicial y sin una persona responsable de capturar cada
entrada, este módulo no funciona.** No es un problema de código. Un inventario
que nadie alimenta da cifras peores que no tener inventario, porque además se
creen. Si esas dos condiciones no se pueden cumplir todavía, conviene dejarlo
parado —no estorba— y hacer antes el módulo de calidad, que sólo necesita el
celular del operador.

## Costeo y rentabilidad

Hoy el sistema no sabe lo que cuesta nada. Sabe kilos y sabe fechas, pero no
hay ni una tarifa ni forma de responder «¿ganamos dinero con esta orden?».

**Este módulo no pide capturar nada al operador.** El material sale del lote
consumido, las horas salen del historial del núcleo y quién trabajó sale de las
asignaciones. Lo único que hay que capturar es cuánto cuesta una hora.

### Puesta en marcha

```bat
.venv\Scripts\python.exe manage.py migrate costeo --database=mes
.venv\Scripts\python.exe manage.py sembrar_costeo
.venv\Scripts\python.exe manage.py sembrar_costeo --tarifa herreria:180:95:120
```

El formato es `linea:hora_maquina:hora_mano_obra:indirectos_hora`. Las tarifas
**no se editan**: para corregir una se captura otra con fecha nueva. Así, si
mañana suben los sueldos, lo que costó una orden del año pasado sigue costando
lo mismo, que es para lo único que sirve un histórico.

Se puede afinar por persona o por rol desde el admin, en «Tarifas de mano de
obra». Si no hay ninguna, se usa la del centro.

### Calcular

```bat
.venv\Scripts\python.exe manage.py calcular_costos --linea herreria
.venv\Scripts\python.exe manage.py calcular_costos --orden H-00020 --varianza
```

No es un asiento contable: es una foto derivada. Se puede recalcular cuando se
quiera, y si aparece un consumo que faltaba, el número que sale es el bueno.

### La columna que hay que mirar primero: cobertura

Dice **qué parte de la orden se pudo medir de verdad**. Baja cuando una etapa
no tiene a nadie asignado, cuando falta la tarifa, o cuando hubo que acotar las
horas. Una cobertura del 20 % significa que el costo es real pero incompleto, y
por tanto que **todavía no sirve para cotizar**.

El módulo no se inventa un operador donde no hay ninguno asignado. Un costo que
parece completo cuando midió la mitad es peor que no tener costo.

### El tope de horas, y por qué existe

> **Aviso importante.** El historial dice cuánto tiempo **pasó** una orden en
> una etapa, no cuánto se **trabajó** en ella. Una orden puede quedarse en
> pintura tres meses esperando material sin que nadie la toque.
>
> Al probarlo con los datos del taller, la orden H-00017 daba **671 horas de
> pintura y 191.274 pesos**. Con el tope aplicado da 7.101 y sale marcada como
> cota, no como medición.

Cada centro de costo tiene un tope de horas por paso, por omisión una jornada
(9 h). Las etapas que lo superan se cobran al tope, se marcan como topadas y no
cuentan como cobertura. El tiempo transcurrido se guarda igual, aparte, porque
es la medida real del flujo y dice cuánto de todo eso fue espera.

El tope se ajusta por centro desde el admin. Se quita del todo capturando
**tiempos estándar**, que es lo que permite distinguir el trabajo de la espera.

### El informe que justifica el módulo

`--varianza` compara lo real contra el tiempo estándar, etapa por etapa. No
dice cuánto cuesta algo: dice **dónde se está perdiendo dinero**. Un costo
absoluto sin nada con qué compararlo no acciona ninguna decisión.

Necesita tiempos estándar capturados (admin → «Tiempos estándar»): cuántas
horas debería llevar una pieza en cada etapa. Es lo siguiente que hay que
capturar después de las tarifas.

### Decisiones que ya están tomadas, y se pueden cambiar

- **Absorbente por omisión**: los indirectos se reparten. `--directo` los deja
  fuera.
- **Los indirectos se prorratean por horas-máquina**, no por toneladas. Una
  pieza pequeña y difícil ocupa la máquina igual que una grande y sencilla;
  prorratear por peso se la regala al cliente equivocado.
- **El material se valúa lote a lote** por antigüedad, no por promedio.

### El margen

`CostoOrden.precio_venta` se puede capturar a mano desde el admin y ya da
margen por orden. Cuando llegue la integración con Cotizaciones, ese precio
vendrá solo de la orden de compra, y entonces el margen real por orden, cliente
y línea sale sin capturar nada.

## Volver atrás

La configuración de entorno no toca la base de datos, así que revertir es
quitar `DJANGO_ENV=prod` del `.bat` y reiniciar. Vuelve a arrancar en modo
desarrollo tal como estaba.
