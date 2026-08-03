"""Inventaría los valores de estado que existen de verdad en la base.

Los estados no son un enumerado: son cadenas sueltas en `estado_etapa` y en
`Viga.estado`, sin `choices`, escritas como literales en unos ciento cuarenta
sitios del código. De ahí salen desalineaciones como "Espera Armado" frente a
"Espera de armado", que el código parchea con `ESTADO_ALIASES` en vigas pero
no en herrería ni en corte láser.

Antes de convertir eso en una máquina de estados como es debido hay que saber
qué hay realmente escrito en producción, no lo que el código supone que hay.
Este informe es el punto de partida de esa migración: cada valor encontrado
tendrá que corresponder con una etapa, incluidos los que nadie recuerda.

    python manage.py auditar_estados
    python manage.py auditar_estados --csv informe_estados.csv
"""
import csv
import unicodedata

from django.core.management.base import BaseCommand
from django.db.models import Count, Max, Min

from catalogos.models import HerrOrdenProduccion, LaserOrdenProduccion, RobotOrdenProduccion
from produccion.models import ESTADOS, Viga

# (etiqueta, modelo, campo)
FUENTES = [
    ("Vigas", Viga, "estado"),
    ("Herrería", HerrOrdenProduccion, "estado_etapa"),
    ("Corte láser", LaserOrdenProduccion, "estado_etapa"),
    ("Herrería (estado general)", HerrOrdenProduccion, "estado"),
    ("Corte láser (estado general)", LaserOrdenProduccion, "estado"),
    ("Robótica (estado general)", RobotOrdenProduccion, "estado"),
]


def normalizar(valor):
    """Minúsculas, sin acentos y sin espacios de más.

    Sirve para agrupar variantes ortográficas del mismo estado y ver cuáles
    son en realidad el mismo concepto escrito de otra forma.
    """
    texto = (valor or "").strip().lower()
    texto = "".join(
        c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn"
    )
    return " ".join(texto.split())


class Command(BaseCommand):
    help = "Lista los valores de estado presentes en la base, con su frecuencia."

    def add_arguments(self, parser):
        parser.add_argument("--csv", dest="ruta_csv", help="Guarda el informe en un CSV.")

    def handle(self, *args, **opciones):
        filas_csv = []
        agrupados = {}

        for etiqueta, modelo, campo in FUENTES:
            self.stdout.write(self.style.MIGRATE_HEADING(f"\n{etiqueta}  ({modelo.__name__}.{campo})"))
            try:
                filas = (
                    modelo.objects.using("mes")
                    .values(campo)
                    .annotate(n=Count("pk"), primero=Min("creado_en" if hasattr(modelo, "creado_en") else "pk"),
                              ultimo=Max("creado_en" if hasattr(modelo, "creado_en") else "pk"))
                    .order_by("-n")
                )
                filas = list(filas)
            except Exception as e:  # noqa: BLE001 - se informa y se sigue
                self.stdout.write(self.style.ERROR(f"  no se pudo consultar: {e}"))
                continue

            if not filas:
                self.stdout.write("  (sin registros)")
                continue

            for fila in filas:
                valor = fila[campo]
                n = fila["n"]
                clave = normalizar(valor)
                agrupados.setdefault(clave, set()).add(repr(valor))
                filas_csv.append(
                    {"fuente": etiqueta, "campo": campo, "valor": valor, "normalizado": clave, "registros": n}
                )
                canonico = valor in ESTADOS if etiqueta == "Vigas" else None
                marca = ""
                if canonico is False:
                    marca = "   <- no está en produccion.ESTADOS"
                self.stdout.write(f"    {str(valor)!r:34} {n:6}{marca}")

        # Variantes ortográficas del mismo estado: el problema que hay que
        # resolver antes de convertir esto en una tabla de etapas.
        self.stdout.write(self.style.MIGRATE_HEADING("\nVariantes del mismo estado"))
        hay_variantes = False
        for clave, escrituras in sorted(agrupados.items()):
            if len(escrituras) > 1:
                hay_variantes = True
                self.stdout.write(self.style.WARNING(f"  {clave!r}: {', '.join(sorted(escrituras))}"))
        if not hay_variantes:
            self.stdout.write("  ninguna: cada estado se escribe siempre igual")

        self.stdout.write(self.style.MIGRATE_HEADING("\nResumen"))
        self.stdout.write(f"  valores distintos: {len({f['valor'] for f in filas_csv})}")
        self.stdout.write(f"  conceptos distintos tras normalizar: {len(agrupados)}")

        if opciones.get("ruta_csv"):
            with open(opciones["ruta_csv"], "w", newline="", encoding="utf-8") as fh:
                escritor = csv.DictWriter(
                    fh, fieldnames=["fuente", "campo", "valor", "normalizado", "registros"]
                )
                escritor.writeheader()
                escritor.writerows(filas_csv)
            self.stdout.write(self.style.SUCCESS(f"\nInforme guardado en {opciones['ruta_csv']}"))
