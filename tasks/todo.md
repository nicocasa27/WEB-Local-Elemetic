# Tareas

El plan de lo que se esté haciendo va aquí, con casillas, **antes** de empezar.
Al terminar, la sección de revisión al final.

---

## En marcha: portal multi-ERP en Supabase + Next.js

Plan aprobado, en `~/.claude/plans/lo-que-me-pasaron-refactored-cocke.md`.
Destino: cero Django, todo en Supabase (Postgres, Auth, Storage, `pg_cron`) con
Next.js sobre Vercel. Camino incremental: Django sigue vivo durante la
transición y muere con la última pantalla.

### Fase 0 · Probar la apuesta antes de casarse con ella

Lo que se puede hacer **sin claves de Supabase**, ensayando contra una base
local desechable. Si el `migrate` limpio en esquemas funciona aquí, funciona
allá: es el mismo PostgreSQL.

- [ ] Base local `mes_ensayo` con los esquemas `plataforma`, `produccion`,
      `rrhh`, `ventas`
- [ ] Configuración de **una sola base** con `search_path=produccion,public`,
      con `default` y `mes` apuntando los dos al mismo sitio
- [ ] **El `migrate` limpio**: `auth` y las 6 apps de negocio en la misma base,
      sin `--fake`. Es el hallazgo que desbloquea la unificación; hay que verlo
      funcionar antes de creérselo
- [ ] Cargar `tests/sql/esquema_heredado.sql` (Django no crea `vigas` ni
      `production_log`: son `managed = False`)
- [ ] Cargar los datos y correr `migrar_auth_a_postgres`
- [ ] **Las 1.004 pruebas contra la base de ensayo**

Lo que **necesita claves** y queda a la espera:

- [ ] Proyecto de Supabase de pruebas, y la suite contra él
- [ ] Los 98 bloques `transaction.atomic`/`select_for_update` contra el
      *pooler*. Modo transacción rompe sentencias preparadas: **no se puede
      saber sin probarlo**, y si falla se replantea
- [ ] `pg_cron` con `consolidar_cierres`

### Hallazgos del ensayo (7 de agosto)

Ensayado contra una base local desechable, `mes_ensayo`, con los cuatro
esquemas. Sin claves de Supabase: es el mismo PostgreSQL, así que lo que falle
aquí falla allá.

**Lo que salió bien**

- **El `migrate` limpio funciona.** 102 tablas —`auth` incluida— en el esquema
  `produccion`, sin un solo `--fake`. La unificación que estaba bloqueada deja
  de estarlo en una base nueva, que era la apuesta del plan.
- **La clave foránea que era imposible ya existe**: `acceso_pin → auth_user` en
  el mismo esquema. Es la que abre la puerta a convertir los 28 campos de
  identidad de texto a relaciones de verdad.
- **Los datos cuadran.** 44 vigas, 155 renglones de bitácora, 85 órdenes del
  núcleo, 325 eventos, 18 personas… y la suma de kilos idéntica al origen.
- La suite sigue en verde en el modo de hoy: **1.115 pruebas**, sin regresión.

**Lo que hubo que arreglar para llegar hasta aquí**

- `tests/sql/esquema_heredado.sql` llevaba **`public.` escrito dentro**, así que
  creaba las tablas heredadas fuera del esquema del ERP dijera lo que dijera el
  `search_path`. Quitado: ahora manda la conexión. Igual en `conftest.py`.
- `settings/test.py` sólo le ponía contraseña a `mes`; con una sola base
  `default` también es PostgreSQL y se quedaba sin ella.

**El hallazgo que corrige el plan**

- [ ] **El paso 6 de la Fase 1 no puede ser un commit aparte.** El plan decía
      conservar `mes` como alias del mismo sitio para no tocar las llamadas
      `.using("mes")`, y **eso no funciona**: Django abre *una conexión por
      alias*, así que son dos transacciones contra la misma base. En la suite
      revienta con `ForeignKeyViolation` (26 fallos, 8 errores, todos en
      almacén), y en producción sería peor: `transaction.atomic(using="mes")`
      dejaría de cubrir lo que se escribe por `default`. Un agujero de
      atomicidad mayor que el de hoy. Probado también con `TEST MIRROR`, que
      tampoco lo arregla: no es cosa de las pruebas.

      Y al revés tampoco se puede adelantar: quitar el `using=` mientras haya
      dos bases reintroduce la «atomicidad falsa» que el proyecto ya arregló, y
      hace saltar su guardia
      (`test_guardias.py::test_las_transacciones_indican_siempre_la_base`).

      **Conclusión: retirar el alias y cambiar de base son un solo movimiento.**
      Más barato de lo que parecía: de las 846 llamadas, **558 pasan por una
      constante** —54 líneas `BASE = "mes"`—, y sólo quedan 264 literales y 57
      `atomic(using="mes")`.

**Una tabla que nadie sabía que estaba**

- [ ] `usuarios_taller` (id, nombre, pin) con 2 filas, en la base del taller.
      **No la menciona ni una línea del repositorio**: ni modelo, ni migración,
      ni documentación. Es anterior al sistema de PIN actual. Hay que decidir
      si viaja a Supabase como tabla heredada o se retira, y eso lo decide el
      taller, no yo. Mientras tanto **no se toca**.

**Dos detalles de herramienta que costarán tiempo si se descubren tarde**

- El `pg_dump` del PATH es la 14 y el servidor local la 18. El del taller es la
  16.9 y Supabase va por la 15/17: **hay que dumpear con la versión del
  destino**, no con la que esté a mano.
- El volcado de PostgreSQL 18 mete metacomandos `\restrict` que `psql` no
  entiende, y `COPY public.` en cada tabla. Los dos hay que limpiarlos para
  cargar en un esquema.

### Fases siguientes

- [ ] **Fase 1** · Una sola base, y Django repuntado a ella
- [ ] **Fase 2** · Plataforma, identidad y portal en Next
- [ ] **Fase 3** · RRHH, el primer ERP nativo
- [ ] **Fase 4** · Producción, de lectura
- [ ] **Fase 5** · La pantalla del piso, como PWA
- [ ] **Fase 6** · Escritura contra el núcleo, y Django se muere

---

## Pendiente

### Del taller

- [ ] **Desplegar en el servidor del taller.** Nada de lo hecho en las últimas
      sesiones está allí todavía. Es lo único que bloquea que llegue a quien lo
      pidió.
- [ ] **Primera ejecución de `INSTALAR.bat` en Windows.** El `.bat`, las
      instalaciones silenciosas de Python y PostgreSQL, la regla del firewall,
      el acceso directo de inicio y `restablecer_password` no se han ejecutado
      nunca en Windows. Conviene estar localizable ese día.
- [ ] **Poner `MES_NUCLEO_*=doble` en el `.env` del taller.** Ahora que `.env`
      se lee de verdad, esto por fin surte efecto.
- [ ] **Asignar los PIN.** 18 cuentas del piso no tienen.
- [ ] **Completar las fichas de personal**: sexo, nacimiento, ingreso, teléfono
      y sueldo. Hasta que no haya sueldos, la nómina sale en cero.
- [ ] **Repasar departamentos y puestos** y quitar los que este taller no use.

### Del sistema

- [ ] **Corte al núcleo unificado**, línea por línea. Va detrás de banderas y no
      se corta hasta 7 días seguidos de `reconciliar_nucleo` sin divergencias.
      Orden: robótica → corta → herrería → vigas.
- [ ] **Los 3 `xfail`**: se resuelven solos al cortar.
- [ ] **Unificar las dos bases** y poner claves foráneas de verdad a `User`.
- [ ] **HTTPS**: 4 avisos de `check --deploy` pendientes, bloqueados por no
      haber un proxy inverso con TLS.

### Preguntas abiertas

- [ ] **Cotización de Corta.mx con varias piezas.** El separador de renglones
      está deducido de una sola muestra, no comprobado. Hace falta un PDF con
      dos o más piezas.
- [ ] **El cliente no viene en la cotización.** Confirmar si alguna otra sí lo
      trae.

---

## Revisión

<!--
  Al cerrar un bloque de trabajo, resumen aquí: qué se hizo, qué se decidió y
  por qué, y qué quedó fuera. Corto.
-->
