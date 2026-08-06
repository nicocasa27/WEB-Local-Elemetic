"""Deja la organización del taller puesta: departamentos, puestos y quién es qué.

La primera versión sólo creaba los cuatro papeles de producción —Soldador,
Auxiliar, Pintor, Operador— que estaban escritos dentro de `Colaborador`, y
dejaba la pantalla con dieciocho personas sin departamento. Servía para no
romper nada y para poco más.

**Nada de lo que hay aquí está inventado.** Sale de lo que el sistema ya sabe
del taller:

- las **etapas** por las que pasa una pieza (`core/estados.py`): espera de
  corte, corte, armado, soldadura, pintura;
- las **áreas** de las cuadrillas que existen: Corte, Soldadura, Pintura;
- las **máquinas** dadas de alta: plasma CNC, pantógrafo de oxicorte, sierra
  cinta, láser de fibra, soldadoras MIG y TIG, cabina de pintura;
- los **roles del sistema** (`core/roles.py`): herrería, robótica, Corta.mx,
  almacén, pedidos y administración.

Es un punto de partida, no una verdad. Lo que sobre se desactiva y lo que falte
se añade desde Recursos humanos → Departamentos y puestos, sin tocar el
programa: para eso se hicieron tablas en vez de listas en el código.

`rol_de_produccion` es lo que hace que esto no rompa nada. El reparto de
órdenes funciona con los cuatro papeles de siempre; cada puesto dice a cuál se
parece. Vacío significa que ese puesto no entra en el reparto de producción,
que es lo que pasa en almacén, en logística y en la oficina.

Es idempotente: correrlo dos veces no duplica nada y no pisa lo que alguien
haya cambiado a mano.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from catalogos.models import Colaborador
from personal.models import Departamento, Puesto, normalizar

#: Los departamentos, en el orden en que pasa el trabajo por ellos.
DEPARTAMENTOS = [
    ("Corte", "Corta el material que llega, antes de armar."),
    ("Armado", "Monta las piezas cortadas antes de soldarlas."),
    ("Soldadura", "Suelda lo armado."),
    ("Pintura", "Prepara y pinta lo soldado."),
    ("Herrería", "Órdenes en serie de herrería."),
    ("Robótica", "Celda robótica."),
    ("Corta.mx", "Pedidos de corte láser."),
    ("Almacén", "Entradas, salidas y surtido de material."),
    ("Logística", "Entrega de producto terminado."),
    ("Administración", "Oficina, ingeniería y supervisión."),
]

#: Los cuatro papeles que ya existían y que el reparto de órdenes usa. Se les
#: pone el departamento en el que se entienden sin más explicación. «Auxiliar»
#: se queda sin ninguno **a propósito**: hay auxiliares en corte, en soldadura
#: y en pintura, y meterlo en uno solo sería mentir sobre los otros dos.
DEPARTAMENTO_DE_LOS_DE_SIEMPRE = {
    "Soldador": "Soldadura",
    "Pintor": "Pintura",
    "Operador": "Corte",
    "Auxiliar": None,
}

#: departamento -> [(puesto, a qué papel de producción se parece)]
PUESTOS = {
    "Corte": [
        ("Operador de plasma", "Operador"),
        ("Operador de oxicorte", "Operador"),
        ("Operador de sierra", "Operador"),
        ("Ayudante de corte", "Auxiliar"),
    ],
    "Armado": [
        ("Armador", "Soldador"),
        ("Ayudante de armado", "Auxiliar"),
    ],
    "Soldadura": [
        ("Soldador MIG", "Soldador"),
        ("Soldador TIG", "Soldador"),
        ("Ayudante de soldadura", "Auxiliar"),
    ],
    "Pintura": [
        ("Preparador de superficie", "Auxiliar"),
        ("Ayudante de pintura", "Auxiliar"),
    ],
    "Herrería": [
        ("Herrero", "Soldador"),
        ("Ayudante de herrería", "Auxiliar"),
    ],
    "Robótica": [
        ("Operador de celda robótica", "Operador"),
    ],
    "Corta.mx": [
        ("Operador de corte láser", "Operador"),
        ("Capturista de pedidos", ""),
    ],
    "Almacén": [
        ("Almacenista", ""),
    ],
    "Logística": [
        ("Chofer", ""),
        ("Auxiliar de logística", ""),
    ],
    "Administración": [
        ("Supervisor de producción", ""),
        ("Ingeniería y proyectos", ""),
        ("Administración", ""),
    ],
}


class Command(BaseCommand):
    help = "Crea los departamentos y puestos del taller y enlaza a quien ya está."

    def handle(self, *args, **opciones):
        creados = {"departamentos": 0, "puestos": 0}
        enlazados = {"puesto": 0, "departamento": 0}

        with transaction.atomic(using="mes"):
            departamentos = {}
            for nombre, descripcion in DEPARTAMENTOS:
                obj, nuevo = Departamento.objects.get_or_create(
                    nombre_normalizado=normalizar(nombre),
                    defaults={"nombre": nombre, "descripcion": descripcion, "activo": True},
                )
                departamentos[nombre] = obj
                creados["departamentos"] += int(nuevo)

            # Los cuatro de siempre. Puede que ya existan de la versión
            # anterior, sin departamento y con gente enlazada: se les pone el
            # suyo sin tocar a nadie.
            for papel, departamento in DEPARTAMENTO_DE_LOS_DE_SIEMPRE.items():
                destino = departamentos.get(departamento) if departamento else None
                obj = Puesto.objects.filter(nombre_normalizado=normalizar(papel)).first()
                if obj is None:
                    Puesto.objects.create(
                        nombre=papel,
                        departamento=destino,
                        rol_de_produccion=papel,
                        activo=True,
                    )
                    creados["puestos"] += 1
                    continue
                campos = []
                if destino and obj.departamento_id is None:
                    obj.departamento = destino
                    campos.append("departamento")
                if not obj.rol_de_produccion:
                    obj.rol_de_produccion = papel
                    campos.append("rol_de_produccion")
                if campos:
                    obj.save(update_fields=campos + ["actualizado_en"])

            for nombre, lista in PUESTOS.items():
                departamento = departamentos[nombre]
                for puesto, papel in lista:
                    _, nuevo = Puesto.objects.get_or_create(
                        nombre_normalizado=normalizar(puesto),
                        departamento=departamento,
                        defaults={
                            "nombre": puesto,
                            "rol_de_produccion": papel,
                            "activo": True,
                        },
                    )
                    creados["puestos"] += int(nuevo)

            # Quien ya estaba: su puesto sale de su rol, y su departamento del
            # área de su cuadrilla. Los dos son datos que ya estaban en la
            # base; aquí sólo se pasan a su sitio.
            for papel, _ in DEPARTAMENTO_DE_LOS_DE_SIEMPRE.items():
                puesto = Puesto.objects.filter(nombre_normalizado=normalizar(papel)).first()
                if puesto:
                    enlazados["puesto"] += Colaborador.objects.filter(
                        rol=papel, puesto__isnull=True
                    ).update(puesto=puesto)

            for ficha in Colaborador.objects.filter(
                departamento__isnull=True
            ).select_related("equipo"):
                area = (getattr(ficha.equipo, "area", "") or "").strip()
                destino = departamentos.get(area) or Departamento.objects.filter(
                    nombre_normalizado=normalizar(area)
                ).first()
                if destino:
                    ficha.departamento = destino
                    ficha.save(update_fields=["departamento", "actualizado_en"])
                    enlazados["departamento"] += 1

        self.stdout.write(f"Departamentos creados: {creados['departamentos']}")
        self.stdout.write(f"Puestos creados: {creados['puestos']}")
        self.stdout.write(f"Personas con su puesto puesto: {enlazados['puesto']}")
        self.stdout.write(f"Personas con su departamento puesto: {enlazados['departamento']}")

        sueltas = Colaborador.objects.filter(activo=True, departamento__isnull=True).count()
        if sueltas:
            self.stdout.write(
                self.style.WARNING(
                    f"Quedan {sueltas} personas activas sin departamento: su cuadrilla "
                    "no coincide con ninguno. Se les pone desde Recursos humanos."
                )
            )
