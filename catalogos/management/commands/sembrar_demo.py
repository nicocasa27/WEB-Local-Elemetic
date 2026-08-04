"""Llena el sistema con un taller simulado, completo y coherente.

«Coherente» es la palabra que hace el trabajo. Es fácil generar mil filas al
azar; el problema es que entonces la pantalla enseña una pieza terminada con
fecha de mañana, una orden con más piezas pintadas que soldadas, y toneladas
que no cuadran con ninguna bitácora. Con datos así no se puede enseñar el
sistema ni practicar con él, porque cada pantalla parece rota.

Aquí cada cosa se genera respetando lo que la haría verdad:

- **Una pieza que va por soldadura tiene bitácora de corte**, con fechas
  crecientes y en horas de jornada. El historial se construye paso a paso, no
  se inventa el estado final.
- **Las fechas de compromiso están repartidas**: unas pocas vencidas, la
  mayoría por delante. Hoy la base real tiene las veintiséis piezas vencidas,
  que es lo mismo que no tener fecha — si todo es urgente, nada lo es.
- **El avance de una orden nunca contradice su etapa**: no hay terminadas sin
  soldar, ni más avance que piezas.
- **El almacén cuadra**: cada existencia viene de una entrada con su lote y su
  costo, así que la trazabilidad de colada funciona de verdad.
- **Todo colaborador del piso tiene cuenta y está enlazado**, que es
  justamente lo que no pasa en la base real y por lo que «Mi trabajo» no se
  usa.

Es determinista: la misma semilla da el mismo taller. Sin eso, un fallo que
sólo aparece con ciertos datos no se puede reproducir.

    manage.py limpiar_datos --si-estoy-seguro mes_vigas
    manage.py sembrar_demo
"""

import random
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from core import estados as est
from core import roles

BASE = "mes"

#: Con la misma semilla sale el mismo taller.
SEMILLA = 20260804

CONTRASENA_DEL_PISO = "taller2026"

# --------------------------------------------------------------- catálogos

PROYECTOS = [
    "PREMIER", "TORRE NORTE", "NAVE ALTABRISA", "PUENTE MOCHIS",
    "BODEGA SUR", "PLANTA MÉRIDA",
]

CLIENTES = [
    "Constructora Altabrisa SA de CV",
    "TL del Sur SA de CV",
    "Grupo Premier",
    "Almaera Industrial",
]

#: Los seis de corte con lo que sabe hacer cada uno. Sin este dato, elegir
#: equipo al lanzar una orden es una lista de seis nombres sin criterio.
MAQUINAS = [
    ("Plasma CNC 1", "Corte", "Placa de 3 a 25 mm", "18", "m/h"),
    ("Plasma CNC 2", "Corte", "Placa de 3 a 25 mm", "18", "m/h"),
    ("Láser fibra 6kW", "Corte", "Lámina hasta 20 mm, corte fino", "42", "m/h"),
    ("Sierra cinta Bekamak", "Corte", "Perfil y tubo hasta 300 mm", "35", "pza/h"),
    ("Cortadora Rotomagic", "Corte", "Redondo y solera hasta 100 mm", "60", "pza/h"),
    ("Pantógrafo oxicorte", "Corte", "Placa gruesa de 25 a 100 mm", "8", "m/h"),
    ("Soldadora MIG 1", "Soldadura", "MIG con Inframix, acero al carbón", "0", ""),
    ("Soldadora MIG 2", "Soldadura", "MIG con Inframix, acero al carbón", "0", ""),
    ("Soldadora TIG", "Soldadura", "TIG, inoxidable y detalle", "0", ""),
    ("Cabina de pintura 1", "Pintura", "Primario y esmalte, piezas hasta 6 m", "0", ""),
]

EQUIPOS = [
    ("Cuadrilla Corte A", "Corte"),
    ("Cuadrilla Soldadura A", "Soldadura"),
    ("Cuadrilla Soldadura B", "Soldadura"),
    ("Cuadrilla Pintura", "Pintura"),
]

#: (nombre, rol, equipo). Nombres inventados.
PERSONAL = [
    ("Juan Pérez Loría", "Soldador", 1),
    ("Miguel Ángel Canul", "Soldador", 1),
    ("Rodrigo Cetina", "Soldador", 2),
    ("Fernando Uc Pech", "Soldador", 2),
    ("Luis Alberto Chan", "Operador", 0),
    ("José Ramón Dzul", "Operador", 0),
    ("Erick Balam", "Operador", 0),
    ("Manuel Ek Poot", "Operador", 0),
    ("Gabriel Tuz", "Operador", 0),
    ("Andrés May Cauich", "Auxiliar", 0),
    ("Pedro Ay Chi", "Auxiliar", 1),
    ("Iván Couoh", "Auxiliar", 1),
    ("Sergio Noh Kú", "Auxiliar", 2),
    ("Ricardo Puc", "Auxiliar", 2),
    ("Omar Cimé", "Auxiliar", 3),
    ("Diana Sosa Ruiz", "Pintor", 3),
    ("Carlos Interián", "Pintor", 3),
    ("Néstor Chablé", "Auxiliar", 3),
]

#: (nombre de la oficina, usuario, rol del sistema)
OFICINA = [
    ("Laura Méndez", "lmendez", "admin_general"),
    ("Roberto Solís", "rsolis", "ingenieria_civil"),
    ("Ana Karina Vega", "avega", "pedidos_ventas"),
    ("Marco Herrera", "mherrera", "almacen"),
    ("Sofía Aguilar", "saguilar", "herreria_supervision"),
    ("Daniel Rosado", "drosado", "corte_laser_supervision"),
]

#: Materia prima. (clave, nombre, unidad, kg por unidad, mínimo, costo)
MATERIALES = [
    ("PL-3/8", "Placa de 3/8 en m²", "m2", "28.60", "12", "1750.00"),
    ("PL-1/2", "Placa de 1/2 en m²", "m2", "38.10", "8", "2270.00"),
    ("PL4X10-1/8", "Lámina 1.2 x 3.05 de 1/8", "pza", "36.50", "20", "1870.00"),
    ("CANALU6", "Canal U de 6 en 12.2 kg/m de 6.1 m", "pza", "74.40", "10", "2610.00"),
    ("HSS4X3/16", "HSS 4 x 3/16 de 6 m", "pza", "51.05", "15", "1980.00"),
    ("RED5/8", "Redondo de 5/8 de 6 m", "pza", "9.30", "24", "230.00"),
    ("SOL1/4X4", "Solera de 1/4 x 4 de 6 m", "pza", "30.20", "12", "800.00"),
    ("CARR45", "Microalambre ER70S-6 de .045, bobina 20 kg", "kg", "1.00", "60", "55.00"),
    ("INFRAMIX", "Mezcla argón-CO2, m³", "m3", "0", "40", "110.00"),
    ("PRIMARIO", "Primario anticorrosivo, litro", "lt", "0", "50", "89.67"),
    ("ESMALTE", "Esmalte alquidálico blanco, litro", "lt", "0", "40", "92.37"),
    ("THINNER", "Thinner, litro", "lt", "0", "30", "30.69"),
    # No inventariables: costos indirectos que OPUS mete en la explosión.
    ("FLETECOMPRA", "Flete de compra de productos", "pza", "0", "0", "0"),
    ("CONSUMIBLES", "Porcentaje de consumibles", "pza", "0", "0", "0"),
]
NO_INVENTARIABLES = {"FLETECOMPRA", "CONSUMIBLES"}

PROVEEDORES = [
    "Aceros del Sureste SA de CV",
    "Ferretería Industrial Mérida",
    "Gases y Soldaduras del Golfo",
]

PIEZAS_HERRERIA = [
    ("Barandal tipo A", "45.20"),
    ("Puerta louver 1.2 x 2.1", "59.00"),
    ("Portón corredizo 4 m", "450.00"),
    ("Andamio estándar galvanizado", "33.20"),
    ("Ancla J de 3/4", "2.40"),
    ("Placa base 300 x 300", "8.60"),
    ("Registro eléctrico 40 x 40", "14.80"),
]

DESCRIPCIONES_VIGA = [
    "HSS 4x3/16", "HSS 6x1/4", "IPR 12x4", "IPR 10x4",
    "Canal U 6", "Ángulo 3x3/8", "Placa 3/8",
]

#: Cuántos **grupos de piezas** hay en cada etapa. Cada grupo son de una a seis
#: piezas del mismo código, así que el total sale bastante mayor.
#:
#: El reparto importa: un taller vivo tiene la mayor parte en proceso y una
#: cola razonable, no todo terminado ni todo esperando. Con todo en una etapa
#: no se puede ver cómo se mueve nada.
REPARTO_DE_ETAPAS = [
    (est.ESPERA_CORTE, 14),
    (est.CORTE, 6),
    (est.ESPERA_ARMADO, 9),
    (est.ARMADO, 5),
    (est.ESPERA_SOLDADURA, 7),
    (est.SOLDADURA, 6),
    (est.ESPERA_PINTURA, 4),
    (est.PINTURA, 4),
    (est.TERMINADO, 12),
    (est.ENVIADO, 8),
]

#: Cuánto se siembra.
#:
#: «chico» es el de por defecto y es el que sirve para **mirar el sistema y
#: entenderlo**: cabe en una pantalla, se puede seguir una pieza entera de
#: principio a fin, y todas las etapas tienen algo. Doscientas piezas enseñan lo
#: mismo pero obligan a paginar y a buscar, que es justo lo que estorba cuando
#: lo que quieres es ver cómo funciona.
#:
#: «completo» es para probar rendimiento y paginación de verdad.
TAMANOS = {
    "chico": {"grupos": 0.28, "ordenes": 6, "dias_cuadrilla": 5, "paros": 6},
    "mediano": {"grupos": 0.6, "ordenes": 10, "dias_cuadrilla": 10, "paros": 12},
    "completo": {"grupos": 1.0, "ordenes": 14, "dias_cuadrilla": 15, "paros": 18},
}


def jornada(dia, azar):
    """Una hora de trabajo verosímil: L-V, 07:30-13:00 y 13:30-17:00.

    Devuelve la hora **local y sin zona**, que es como guardan las tablas
    heredadas `vigas` y `production_log`: sus columnas son
    `timestamp without time zone`.

    Esto importa y ya mordió una vez. Con `USE_TZ = True`, si aquí se
    devolviera una fecha con zona, Django la convertiría a UTC antes de
    escribirla en una columna que no guarda zona: un movimiento de las 08:00
    en Mérida quedaría grabado como las 14:00, y al leerlo otra vez saldría a
    las 14:00. Seis horas de corrimiento en toda la bitácora, y los
    indicadores de jornada calculando sobre horas que nadie trabajó.

    Para las tablas que sí maneja Django —los paros, por ejemplo— hay que
    envolverlo con `timezone.make_aware`, y por eso existe `con_zona`.

    Que los sellos caigan en horario laboral no es cosmético: los indicadores
    de disponibilidad y los tiempos por etapa se calculan descontando lo que
    queda fuera de la jornada.
    """
    while dia.weekday() >= 5:
        dia -= timedelta(days=1)
    if azar.random() < 0.6:
        hora = time(azar.randint(7, 12), azar.randint(0, 59))
    else:
        hora = time(azar.randint(13, 16), azar.randint(0, 59))
    return datetime.combine(dia, hora)


def con_zona(momento):
    """La misma hora, para las tablas que sí guardan zona."""
    return timezone.make_aware(momento)


def usuario_desde(texto):
    """Un nombre de cuenta tecleable: sin tildes, sin eñes y sin espacios.

    En Python la «í» es alfanumérica, así que el filtro obvio la deja pasar y
    sale «jloría». En el piso esa cuenta se teclea con guantes en el teclado de
    un celular, y una tilde es tres pulsaciones más y un error probable.
    """
    import unicodedata

    plano = unicodedata.normalize("NFD", texto.lower())
    plano = "".join(c for c in plano if unicodedata.category(c) != "Mn")
    return "".join(c for c in plano if c.isascii() and c.isalnum())


class Command(BaseCommand):
    help = "Llena el sistema con un taller simulado, completo y coherente."

    def add_arguments(self, parser):
        parser.add_argument("--semilla", type=int, default=SEMILLA)
        parser.add_argument(
            "--tamano",
            choices=sorted(TAMANOS),
            default="chico",
            help=(
                "Cuánto sembrar. «chico» (por defecto) cabe en una pantalla y "
                "sirve para entender el sistema; «completo» es para probar "
                "paginación y rendimiento."
            ),
        )
        parser.add_argument(
            "--sin-usuarios",
            action="store_true",
            help="No crea cuentas para el personal del piso.",
        )

    @transaction.atomic(using=BASE)
    def handle(self, *args, **opciones):
        self.azar = random.Random(opciones["semilla"])
        self.hoy = timezone.localdate()
        self.tamano = TAMANOS[opciones["tamano"]]

        self.stdout.write(self.style.MIGRATE_HEADING("\nConfiguración base"))
        call_command("sembrar_nucleo", verbosity=0)
        call_command("sembrar_inventario", verbosity=0)
        roles.asegurar_grupos()
        call_command("crear_admin", verbosity=0)
        self.stdout.write("  núcleo, inventario, grupos y administrador")

        self.stdout.write(self.style.MIGRATE_HEADING("\nTaller"))
        self._proyectos()
        self._maquinas()
        equipos = self._equipos()
        personal = self._personal(equipos, opciones["sin_usuarios"])
        self._oficina(opciones["sin_usuarios"])

        self.stdout.write(self.style.MIGRATE_HEADING("\nAlmacén"))
        materiales = self._materiales()
        self._lotes_y_existencias(materiales)
        self._listas_de_materiales(materiales)

        self.stdout.write(self.style.MIGRATE_HEADING("\nProducción"))
        self._vigas()
        self._herreria()
        self._cuadrillas(equipos, personal)
        self._paros()

        self.stdout.write(self.style.SUCCESS("\nTaller simulado listo.\n"))
        self._resumen()

    # ------------------------------------------------------------- taller

    def _proyectos(self):
        from catalogos.models import Proyecto

        for nombre in PROYECTOS:
            Proyecto.objects.using(BASE).get_or_create(
                nombre_normalizado=nombre.upper(), defaults={"nombre": nombre}
            )
        self.stdout.write(f"  {len(PROYECTOS)} proyectos")

    def _maquinas(self):
        from catalogos.models import Maquina

        for nombre, tipo, funcion, capacidad, unidad in MAQUINAS:
            Maquina.objects.using(BASE).update_or_create(
                nombre=nombre,
                defaults={
                    "tipo": tipo,
                    "funcion": funcion,
                    "capacidad_hora": Decimal(capacidad),
                    "capacidad_unidad": unidad,
                    "activo": True,
                },
            )
        self.stdout.write(f"  {len(MAQUINAS)} máquinas, con su función y capacidad")

    def _equipos(self):
        from catalogos.models import EquipoTrabajo

        equipos = []
        for nombre, area in EQUIPOS:
            equipo, _ = EquipoTrabajo.objects.using(BASE).get_or_create(
                nombre=nombre, defaults={"area": area, "integrantes": 0}
            )
            equipos.append(equipo)
        return equipos

    def _personal(self, equipos, sin_usuarios):
        """El piso, con cuenta y enlazado.

        Es justo lo que no pasa en la base real: los once usuarios son de
        oficina, así que los movimientos los captura un supervisor y la
        trazabilidad dice quién capturó, no quién hizo.
        """
        from catalogos.models import Colaborador

        Usuario = get_user_model()
        gente = []
        for nombre, rol, indice in PERSONAL:
            equipo = equipos[indice]
            partes = nombre.lower().split()
            cuenta = usuario_desde(f"{partes[0][0]}{partes[-1]}")

            colaborador, _ = Colaborador.objects.using(BASE).get_or_create(
                nombre=nombre,
                defaults={"rol": rol, "equipo": equipo, "activo": True},
            )

            if not sin_usuarios:
                usuario, nuevo = Usuario.objects.get_or_create(
                    username=cuenta,
                    defaults={"first_name": partes[0].title(), "is_active": True},
                )
                if nuevo:
                    usuario.set_password(CONTRASENA_DEL_PISO)
                    usuario.save()
                from django.contrib.auth.models import Group

                grupo = "corte" if rol == "Operador" else "soldadura"
                usuario.groups.set(Group.objects.filter(name=grupo))
                colaborador.usuario = cuenta
                colaborador.save(using=BASE, update_fields=["usuario"])

            gente.append(colaborador)

        self._ajustar_integrantes(equipos)
        if sin_usuarios:
            self.stdout.write(f"  {len(gente)} personas del piso, sin cuenta")
        else:
            self.stdout.write(
                f"  {len(gente)} personas del piso, todas con cuenta y enlazadas "
                f"(contraseña «{CONTRASENA_DEL_PISO}»)"
            )
        return gente

    def _ajustar_integrantes(self, equipos):
        for equipo in equipos:
            equipo.integrantes = equipo.colaboradores.using(BASE).filter(activo=True).count()
            equipo.save(using=BASE, update_fields=["integrantes"])

    def _oficina(self, sin_usuarios):
        if sin_usuarios:
            return
        from django.contrib.auth.models import Group

        Usuario = get_user_model()
        for nombre, cuenta, grupo in OFICINA:
            usuario, nuevo = Usuario.objects.get_or_create(
                username=cuenta,
                defaults={
                    "first_name": nombre.split()[0],
                    "last_name": " ".join(nombre.split()[1:]),
                    "is_active": True,
                },
            )
            if nuevo:
                usuario.set_password(CONTRASENA_DEL_PISO)
                usuario.save()
            usuario.groups.set(Group.objects.filter(name=grupo))
            usuario.is_staff = grupo in roles.QUE_ADMINISTRAN
            usuario.save(update_fields=["is_staff"])
        self.stdout.write(f"  {len(OFICINA)} cuentas de oficina")

    # ------------------------------------------------------------ almacén

    def _materiales(self):
        from inventario.models import Material

        creados = {}
        for clave, nombre, unidad, peso, minimo, _costo in MATERIALES:
            material, _ = Material.objects.using(BASE).update_or_create(
                codigo=clave,
                defaults={
                    "nombre": nombre,
                    "nombre_normalizado": nombre.upper(),
                    "unidad": unidad if unidad in dict(Material.Unidad.choices) else "pza",
                    "peso_kg": Decimal(peso),
                    "stock_minimo": Decimal(minimo),
                    "inventariable": clave not in NO_INVENTARIABLES,
                    "activo": True,
                },
            )
            creados[clave] = material
        self.stdout.write(
            f"  {len(creados)} materiales "
            f"({len(NO_INVENTARIABLES)} marcados como no inventariables)"
        )
        return creados

    def _lotes_y_existencias(self, materiales):
        """Cada existencia viene de una entrada con lote y costo.

        Poner el número a mano en `Existencia` sería más rápido y dejaría el
        almacén sin historia: no se podría decir de qué colada salió una pieza
        ni cuánto costó de verdad, que es el motivo de que el lote exista.
        """
        from core.servicios import inventario as servicio
        from inventario.models import LoteMaterial, Proveedor

        proveedores = []
        for nombre in PROVEEDORES:
            proveedor, _ = Proveedor.objects.using(BASE).get_or_create(
                nombre_normalizado=nombre.upper(), defaults={"nombre": nombre}
            )
            proveedores.append(proveedor)

        almacen = servicio.almacen_principal()
        lotes = 0
        for (clave, _n, _u, _p, minimo, costo) in MATERIALES:
            if clave in NO_INVENTARIABLES:
                continue
            material = materiales[clave]
            objetivo = Decimal(minimo) * Decimal(self.azar.choice(["1.4", "2.2", "3.0", "0.8"]))
            for numero in range(self.azar.randint(1, 3)):
                dias = self.azar.randint(10, 180)
                lote = LoteMaterial.objects.using(BASE).create(
                    material=material,
                    codigo=f"{clave}-L{numero + 1}",
                    colada=f"C{self.azar.randint(100000, 999999)}",
                    costo_unitario=Decimal(costo) * Decimal(
                        self.azar.choice(["0.94", "1.0", "1.07"])
                    ),
                    proveedor=self.azar.choice(proveedores),
                    recibido_en=self.hoy - timedelta(days=dias),
                )
                cantidad = (objetivo / 2).quantize(Decimal("0.01"))
                if cantidad > 0:
                    servicio.registrar_entrada(
                        lote=lote, cantidad=cantidad, actor=None, almacen=almacen
                    )
                    lotes += 1
        bajos = len(servicio.bajo_minimo(almacen))
        self.stdout.write(
            f"  {lotes} lotes con entrada y colada · {bajos} materiales bajo mínimo"
        )

    def _listas_de_materiales(self, materiales):
        """Las recetas de la manufactura en serie.

        Sin ellas, la Rama A no puede reservar material al lanzar una orden:
        no hay forma de saber qué lleva un andamio.
        """
        from inventario.models import ListaMateriales, RenglonListaMateriales
        from nucleo.models import LineaNegocio, PiezaCatalogo

        linea = LineaNegocio.objects.using(BASE).filter(codigo="herreria").first()
        if linea is None:
            return

        recetas = {
            "Barandal tipo A": [("HSS4X3/16", "1.5"), ("RED5/8", "4"), ("CARR45", "0.8"), ("PRIMARIO", "1.2")],
            "Puerta louver 1.2 x 2.1": [("PL4X10-1/8", "1.2"), ("SOL1/4X4", "2"), ("CARR45", "1.1"), ("ESMALTE", "1.5")],
            "Portón corredizo 4 m": [("HSS4X3/16", "6"), ("PL-3/8", "1.4"), ("CARR45", "3.2"), ("PRIMARIO", "4")],
            "Andamio estándar galvanizado": [("HSS4X3/16", "2.4"), ("RED5/8", "6"), ("CARR45", "1.4")],
            "Ancla J de 3/4": [("RED5/8", "0.35")],
            "Placa base 300 x 300": [("PL-3/8", "0.09")],
            "Registro eléctrico 40 x 40": [("PL4X10-1/8", "0.3"), ("ESMALTE", "0.4")],
        }

        hechas = 0
        for nombre, peso in PIEZAS_HERRERIA:
            pieza, _ = PiezaCatalogo.objects.using(BASE).get_or_create(
                linea=linea,
                nombre_normalizado=nombre.upper(),
                defaults={"nombre": nombre, "peso_kg": Decimal(peso)},
            )
            lista, _ = ListaMateriales.objects.using(BASE).get_or_create(
                pieza=pieza, version=1, defaults={"vigente": True}
            )
            for clave, cantidad in recetas.get(nombre, []):
                material = materiales.get(clave)
                if material is None:
                    continue
                RenglonListaMateriales.objects.using(BASE).get_or_create(
                    lista=lista, material=material,
                    defaults={"cantidad_por_pieza": Decimal(cantidad)},
                )
            hechas += 1
        self.stdout.write(f"  {hechas} listas de materiales")

    # --------------------------------------------------------- producción

    def _fecha_de_compromiso(self):
        """Repartidas, no todas vencidas.

        En la base real las veintiséis piezas están vencidas, que es lo mismo
        que no tener fecha: si todo es urgente, no se puede priorizar. Aquí una
        de cada seis va tarde, que es lo que tiene un taller que va apretado
        pero al día.
        """
        tirada = self.azar.random()
        if tirada < 0.17:
            return self.hoy - timedelta(days=self.azar.randint(1, 20))
        if tirada < 0.30:
            return self.hoy + timedelta(days=self.azar.randint(0, 3))
        return self.hoy + timedelta(days=self.azar.randint(4, 45))

    def _vigas(self):
        """Piezas con su historia, no sólo con su estado.

        Se recorre la secuencia desde el principio y se va dejando bitácora
        hasta la etapa que le toca. Así una pieza en pintura tiene apuntes de
        corte, armado y soldadura, con fechas crecientes y en jornada.
        """
        from produccion.models import ProductionLog, Viga

        secuencia = est.SECUENCIA
        creadas = apuntes = 0

        escala = self.tamano["grupos"]
        for estado_final, cuantas in REPARTO_DE_ETAPAS:
            objetivo = secuencia.index(estado_final)
            # Al menos un grupo por etapa aunque la escala sea pequeña:
            # una etapa vacía no se puede explorar.
            for _ in range(max(1, round(cuantas * escala))):
                proyecto = self.azar.choice(PROYECTOS)
                total = self.azar.choice([1, 1, 2, 2, 3, 4])
                letra = self.azar.choice("ABCDEFGH")
                descripcion = self.azar.choice(DESCRIPCIONES_VIGA)
                peso = Decimal(self.azar.choice(
                    ["18.40", "27.90", "38.55", "50.96", "51.05", "74.20", "96.10"]
                ))
                # Los saltos entre etapas se deciden **antes** de elegir la
                # fecha de alta, y el alta se coloca hacia atrás lo suficiente
                # para que el último paso caiga hoy o antes.
                #
                # Al revés —fecha primero y saltos después— la cadena se
                # pasaba de hoy: una pieza enviada podía tener nueve saltos de
                # hasta cuatro días cada uno y acabar con movimientos de la
                # semana que viene. Una bitácora del futuro no es un detalle:
                # los informes semanales la cuentan en semanas que no han
                # pasado.
                saltos = [self.azar.randint(1, 4) for _ in range(objetivo)]
                margen = self.azar.randint(1, 6)
                creada = jornada(
                    self.hoy - timedelta(days=sum(saltos) + margen), self.azar
                )

                for numero in range(1, total + 1):
                    pieza = Viga.objects.using(BASE).create(
                        codigo_viga=f"{descripcion.split()[0]}-{letra}",
                        pieza_no=numero,
                        total_piezas=total,
                        proyecto=proyecto,
                        descripcion=descripcion,
                        fecha_compromiso=self._fecha_de_compromiso(),
                        estado=est.ESPERA_CORTE,
                        prioridad=self.azar.choice([1, 2, 2, 3, 3, 3]),
                        peso_kg=peso,
                        fecha_creacion=creada,
                        ultimo_cambio=creada,
                    )
                    creadas += 1

                    # Se lleva la fecha aparte y siempre avanza al menos un
                    # día. Antes, cuando un paso caía antes que el anterior se
                    # le sumaban dos horas, y encadenando varios el sello se
                    # salía de la jornada y acababa en sábado.
                    dia_del_paso = creada.date()
                    for indice in range(objetivo):
                        dia_del_paso += timedelta(days=saltos[indice])
                        momento = jornada(dia_del_paso, self.azar)
                        dia_del_paso = momento.date()
                        anterior, nuevo = secuencia[indice], secuencia[indice + 1]
                        ProductionLog.objects.using(BASE).create(
                            viga_internal_id=pieza.internal_id,
                            estado_anterior=anterior,
                            estado_nuevo=nuevo,
                            fecha_operacion=momento.date(),
                            timestamp=momento,
                            comentario="",
                        )
                        apuntes += 1
                        pieza.estado = nuevo
                        pieza.ultimo_cambio = momento

                    Viga.objects.using(BASE).filter(pk=pieza.pk).update(
                        estado=pieza.estado, ultimo_cambio=pieza.ultimo_cambio
                    )

        self.stdout.write(f"  {creadas} piezas de estructuras · {apuntes} apuntes de bitácora")

    def _herreria(self):
        """Órdenes con avance que no se contradice.

        La invariante que la base real no tiene: terminadas ≤ pintadas ≤
        soldadas ≤ total. Sin respetarla salen órdenes con material terminado
        que nunca se soldó.
        """
        from catalogos.models import HerrCliente, HerrOrdenProduccion, Proyecto

        proyectos = list(Proyecto.objects.using(BASE).all())
        clientes = []
        for nombre in CLIENTES:
            cliente, _ = HerrCliente.objects.using(BASE).get_or_create(
                nombre_normalizado=nombre.upper(), defaults={"nombre": nombre}
            )
            clientes.append(cliente)

        etapas = [est.ESPERA_CORTE, est.CORTE, est.SOLDADURA, est.SOLDADURA,
                  est.PINTURA, est.TERMINADO]
        creadas = 0
        for numero in range(1, self.tamano["ordenes"] + 1):
            nombre, peso_pieza = self.azar.choice(PIEZAS_HERRERIA)
            total = self.azar.choice([2, 4, 8, 12, 20, 30, 70])
            etapa = self.azar.choice(etapas)

            if etapa in (est.ESPERA_CORTE, est.CORTE):
                soldadas = pintadas = terminadas = 0
            elif etapa == est.SOLDADURA:
                soldadas = self.azar.randint(1, total)
                pintadas = self.azar.randint(0, soldadas)
                terminadas = self.azar.randint(0, pintadas)
            elif etapa == est.PINTURA:
                soldadas = total
                pintadas = self.azar.randint(total // 2, total)
                terminadas = self.azar.randint(0, pintadas)
            else:
                soldadas = pintadas = terminadas = total

            HerrOrdenProduccion.objects.using(BASE).create(
                codigo=f"H-{numero:05d}",
                codigo_normalizado=f"H-{numero:05d}",
                nombre=nombre,
                nombre_normalizado=nombre.upper(),
                descripcion=nombre,
                cliente_herreria=self.azar.choice(clientes),
                proyecto=self.azar.choice(proyectos) if proyectos else None,
                pieza_no=1,
                total_piezas=total,
                peso_kg=Decimal(peso_pieza) * total,
                fecha_compromiso=self._fecha_de_compromiso(),
                prioridad=self.azar.choice([1, 2, 3, 3]),
                estado_etapa=etapa,
                es_op=total > 1,
                es_individual=total == 1,
                cantidad_objetivo=total,
                cantidad_producida=soldadas,
                cantidad_pintada=pintadas,
                cantidad_terminada=terminadas,
                ultimo_cambio=timezone.now(),
            )
            creadas += 1
        self.stdout.write(f"  {creadas} órdenes de herrería con avance coherente")

    def _cuadrillas(self, equipos, personal):
        """Quince días de cuadrillas, con la gente que «se presentó»."""
        from catalogos.models import Cuadrilla, CuadrillaIntegrante, Maquina

        por_area = {}
        for colaborador in personal:
            por_area.setdefault(colaborador.equipo.area, []).append(colaborador)

        maquinas_corte = list(
            Maquina.objects.using(BASE).filter(tipo="Corte", activo=True)
        )
        armadas = integrantes = 0
        dia = self.hoy
        for _ in range(self.tamano["dias_cuadrilla"]):
            while dia.weekday() >= 5:
                dia -= timedelta(days=1)
            for area, gente in por_area.items():
                if not gente:
                    continue
                maquina = (
                    self.azar.choice(maquinas_corte)
                    if area == "Corte" and maquinas_corte else None
                )
                cuadrilla, nueva = Cuadrilla.objects.using(BASE).get_or_create(
                    fecha=dia,
                    turno=Cuadrilla.Turno.COMPLETO,
                    centro=area if area in dict(Maquina.TIPO_CHOICES) else "Soldadura",
                    maquina=maquina,
                    defaults={"armada_por": "sembrar_demo"},
                )
                if not nueva:
                    continue
                armadas += 1
                # No se presenta todo el mundo todos los días: eso es
                # justamente lo que la plantilla fija no sabía representar.
                presentes = self.azar.sample(gente, k=max(1, len(gente) - self.azar.randint(0, 2)))
                for colaborador in presentes:
                    CuadrillaIntegrante.objects.using(BASE).create(
                        cuadrilla=cuadrilla,
                        colaborador=colaborador,
                        papel=colaborador.rol,
                        fraccion=Decimal(self.azar.choice(["1.00", "1.00", "1.00", "0.50"])),
                    )
                    integrantes += 1
            dia -= timedelta(days=1)
        self.stdout.write(f"  {armadas} cuadrillas · {integrantes} participaciones")

    def _paros(self):
        from catalogos.models import Maquina, MaquinaParo, MaquinaParoMotivo

        motivos = list(MaquinaParoMotivo.objects.using(BASE).all()[:6])
        if not motivos:
            for nombre in ["Falta de material", "Mantenimiento", "Falla eléctrica",
                           "Cambio de herramienta", "Sin energía"]:
                motivos.append(MaquinaParoMotivo.objects.using(BASE).create(
                    nombre=nombre, nombre_normalizado=nombre.upper()
                ))

        maquinas = list(Maquina.objects.using(BASE).filter(activo=True))
        creados = 0
        for _ in range(self.tamano["paros"]):
            maquina = self.azar.choice(maquinas)
            inicio = con_zona(
                jornada(self.hoy - timedelta(days=self.azar.randint(1, 25)), self.azar)
            )
            MaquinaParo.objects.using(BASE).create(
                maquina=maquina,
                motivo=self.azar.choice(motivos),
                inicio=inicio,
                fin=inicio + timedelta(minutes=self.azar.choice([20, 45, 90, 150, 240])),
                registrado_por="sembrar_demo",
            )
            creados += 1
        self.stdout.write(f"  {creados} paros de máquina cerrados")

    # ------------------------------------------------------------ resumen

    def _resumen(self):
        from catalogos.models import Colaborador

        Usuario = get_user_model()
        sin_cuenta = Colaborador.objects.using(BASE).filter(activo=True, usuario="").count()

        # La cuenta del piso se busca en la base en vez de escribirla aquí: el
        # nombre lo genera `_personal` a partir del nombre completo, y anunciar
        # uno a mano acaba anunciando una cuenta que no existe.
        soldador = (
            Colaborador.objects.using(BASE)
            .filter(rol="Soldador", activo=True).exclude(usuario="").first()
        )

        self.stdout.write("  Entra con:")
        self.stdout.write("    admin / Elemetic2026!      (administrador fijo)")
        self.stdout.write(f"    lmendez / {CONTRASENA_DEL_PISO}      (administración)")
        self.stdout.write(f"    mherrera / {CONTRASENA_DEL_PISO}     (almacén)")
        if soldador:
            self.stdout.write(
                f"    {soldador.usuario} / {CONTRASENA_DEL_PISO}"
                f"{' ' * max(1, 9 - len(soldador.usuario))}"
                f"({soldador.nombre}, «Mi trabajo»)"
            )
        self.stdout.write(f"\n  {Usuario.objects.count()} cuentas · "
                          f"{sin_cuenta} personas del taller sin cuenta\n")
