# MES de Taller Elemetic

Sistema de producción de un taller metalúrgico: órdenes, avance por etapas,
almacén de producto terminado, inventario de materia prima, costeo e
indicadores. Corre en **una** computadora del taller y todos los demás entran
desde el navegador, incluidos los celulares del piso.

> ⚠️ **Este repositorio es privado y tiene que seguir siéndolo.** Dentro del
> código están, en claro, la contraseña del administrador del taller
> (`catalogos/management/commands/crear_admin.py`) y la del piso
> (`catalogos/management/commands/sembrar_demo.py`). Es así a petición del taller, que quería poder
> entrar sin depender de nadie. Mientras eso no cambie, el repositorio no puede
> hacerse público.

---

## Por dónde empezar, según quién seas

| Si eres… | Lee |
|---|---|
| La persona que va a instalarlo y no programa | [`LEEME-PRIMERO.txt`](LEEME-PRIMERO.txt) |
| Quien mantiene el servidor | [`DESPLIEGUE.md`](DESPLIEGUE.md) |
| Quien toca la base de datos | [`docs/BD_Y_MIGRACIONES.md`](docs/BD_Y_MIGRACIONES.md) |

En Windows la instalación es **doble clic en `INSTALAR.bat`** y darle a *Sí* al
aviso de administrador. No pregunta nada más: si falta Python o PostgreSQL, los
instala; monta el entorno, crea la base, abre el puerto en el Firewall y deja el
sistema arrancando solo al encender la máquina.

---

## Cómo está montado

- **Django 5.2 · Python 3.12 · PostgreSQL** — sin framework de frontend, sin
  build pipeline, sin CDN. El taller trabaja **sin internet**: todo lo que
  necesita el navegador está servido desde disco con `whitenoise`, y hay un test
  (`tests/test_sin_internet.py`) que lo vigila.
- **Dos bases de datos.** `default` (SQLite) guarda cuentas, sesiones y PIN;
  `mes` (PostgreSQL) guarda todo lo del negocio. Las reparte
  `mes_vigas_web/db_router.py`. Unificarlas está pendiente y explicado en
  `DESPLIEGUE.md`.
- **Tablas heredadas.** `vigas` y `production_log` son `managed = False`: existen
  desde antes y no se les pueden añadir columnas. Su esquema real está
  versionado en `tests/sql/esquema_heredado.sql`, que además es su única
  documentación.

### Las apps

| App | Qué hace |
|---|---|
| `catalogos` | Clientes, proyectos, máquinas, colaboradores, órdenes de herrería y corte láser |
| `produccion` | Vigas, tablero, dashboard, pantalla móvil del piso |
| `nucleo` | El motor unificado al que están migrando las cuatro líneas |
| `inventario` | Materia prima, lotes, movimientos |
| `costeo` | Costo por orden |
| `acceso` | Entrar con un PIN de cuatro dígitos desde la tableta del piso |
| `core/` | Servicios, estados, roles y banderas. **La lógica vive aquí, no en las vistas.** |

### Dos ideas que explican casi todo el código

**Derivar, no copiar.** La bandeja de despacho, las compras, el stock de
producto terminado, el avance de un proyecto y los indicadores de rendimiento
**se calculan**, no se guardan. Un dato guardado en dos sitios acaba
divergiendo, y aquí ya pasó.

**Un `git revert` del código tiene que dejar el sistema funcionando sin tocar la
base.** De ahí que no haya migraciones destructivas: solo `AddField`,
`CreateModel`, `AddIndex`, `AddConstraint`.

---

## Desarrollo

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt

export DJANGO_ENV=dev
export MES_DB_NAME=mes_vigas MES_DB_USER=postgres MES_DB_HOST=127.0.0.1

python manage.py migrate                    # primero la base `default`
python manage.py migrate --database=mes     # y luego la de negocio
python manage.py crear_admin
python manage.py runserver
```

El orden de las dos migraciones importa: al revés falla con
`no such table: auth_group`.

La configuración también se puede dejar en un archivo `.env` en la raíz, que
`mes_vigas_web/settings/__init__.py` lee al arrancar. **Lo que ya esté en el
entorno manda sobre el `.env`.**

### Pruebas

```bash
pytest            # ~974 pruebas, 3 xfail conocidos
```

Los 3 `xfail` documentan bugs del motor viejo que quedan resueltos al cortar al
núcleo. Hacen falta PostgreSQL y una base `test_mes_vigas` que se pueda crear.

Cuatro de las pruebas no comprueban un caso sino una **propiedad estructural**,
y son las que más han encontrado:

- toda vista ruteada tiene `login_required`;
- ningún `transaction.atomic()` sin `using=`, que sobre dos bases no es atómico;
- ningún `except` que se trague el error sin dejar rastro en el registro;
- ningún comentario `{# … #}` de varias líneas, que Django imprime en la página.

---

## Estado

En marcha en el taller: órdenes de las cuatro líneas, almacén, despacho,
expedientes, dashboard, PIN del piso, entrega firmada entre áreas y rendimiento
por persona.

Pendiente:

- **Corte al núcleo unificado**, línea por línea. Va detrás de banderas
  (`MES_NUCLEO_<LINEA>`) y no se corta hasta 7 días seguidos de
  `reconciliar_nucleo` sin divergencias. Orden: robótica → corta → herrería →
  vigas.
- **Unificar las dos bases** y poner claves foráneas de verdad a `User`.
- **HTTPS**, que depende de que haya un proxy inverso con TLS.

---

## Lo que no viaja en el repositorio, a propósito

`media/` (planos y acuses), `db.sqlite3` (cuentas y PIN) y la base de PostgreSQL.
Ninguno se puede recuperar desde aquí. Antes de tocar el servidor, respaldar;
cómo, está en `DESPLIEGUE.md`.
