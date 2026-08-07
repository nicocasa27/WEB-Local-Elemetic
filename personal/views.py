"""Recursos humanos: la gente del taller, sus datos y su sueldo.

Lo que había antes: una ficha con nombre, equipo y un rol de cuatro opciones,
que se daba de alta desde la pantalla de Equipos porque era donde cabía. No se
podía contestar cuánta gente hay, en qué departamento está, ni cuánto suma la
nómina, y los datos de la persona —cuándo nació, cuándo entró, cuánto gana— no
existían en ninguna parte.

Tres pantallas:

- **Personal**: quién hay, con lo que suma la nómina y el reparto por
  departamento. Los números se calculan aquí, no se guardan: un total guardado
  es un total que se queda viejo.
- **Ficha**: alta y edición de una persona, con su cuenta para entrar al
  sistema si la necesita. La cuenta se crea desde aquí porque la alternativa
  —dar de alta a alguien, irse a Usuarios, buscarlo y enlazarlo— es donde se
  pierden los enlaces, y sin enlace «Mi trabajo» no le enseña sus órdenes.
- **Organización**: departamentos y puestos, para que añadir «Pailero» no
  signifique tocar el programa.

**El sueldo sólo lo ve quien administra.** No es una precaución teórica: en el
taller la pantalla se abre delante de otros.
"""

from decimal import Decimal

from django import forms
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST, require_http_methods

from acceso import servicios as pines
from catalogos.models import Colaborador, EquipoTrabajo
from catalogos.usuarios import _aplicar_grupos, _guardar_enlace, _guardar_pin
from core import roles
from core.campos import CampoDeFecha
from personal.models import Departamento, Puesto, normalizar
from core.bases import BASE  # noqa: F401

Usuario = get_user_model()


solo_administradores = user_passes_test(
    roles.puede_administrar_usuarios, login_url="login"
)


# ------------------------------------------------------------- formularios


class FichaForm(forms.ModelForm):
    """La persona. Todo lo de recursos humanos menos su cuenta."""

    class Meta:
        model = Colaborador
        fields = [
            "nombre",
            "sexo",
            "fecha_nacimiento",
            "telefono",
            "departamento",
            "puesto",
            "equipo",
            "fecha_ingreso",
            "sueldo_mensual",
            "activo",
        ]
        labels = {
            "nombre": "Nombre completo",
            "sexo": "Sexo",
            "fecha_nacimiento": "Fecha de nacimiento",
            "telefono": "Teléfono",
            "departamento": "Departamento",
            "puesto": "Puesto",
            "equipo": "Equipo de trabajo",
            "fecha_ingreso": "Fecha de ingreso",
            "sueldo_mensual": "Sueldo mensual",
            "activo": "Sigue trabajando aquí",
        }
        help_texts = {
            "equipo": "En qué cuadrilla trabaja. De aquí sale el reparto de órdenes.",
            "sueldo_mensual": "Bruto al mes. Sólo lo ve quien administra.",
            "activo": "Al desmarcarlo deja de aparecer para asignar trabajo. No se borra nada.",
        }
        widgets = {
            "fecha_nacimiento": CampoDeFecha(),
            "fecha_ingreso": CampoDeFecha(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["departamento"].queryset = Departamento.objects.filter(activo=True)
        self.fields["departamento"].empty_label = "— Sin departamento —"
        self.fields["departamento"].required = False
        self.fields["puesto"].queryset = Puesto.objects.filter(activo=True).select_related(
            "departamento"
        )
        self.fields["puesto"].empty_label = "— Sin puesto —"
        self.fields["puesto"].required = False
        self.fields["equipo"].queryset = EquipoTrabajo.objects.filter(activo=True)
        self.fields["sueldo_mensual"].required = False

        for nombre, campo in self.fields.items():
            if nombre == "activo":
                campo.widget.attrs.setdefault("class", "form-check-input")
            elif isinstance(campo.widget, forms.Select):
                campo.widget.attrs.setdefault("class", "form-select")
            else:
                campo.widget.attrs.setdefault("class", "form-control")

    def clean_nombre(self):
        nombre = (self.cleaned_data.get("nombre") or "").strip()
        if not nombre:
            raise forms.ValidationError("El nombre hace falta.")
        repetido = Colaborador.objects.filter(nombre__iexact=nombre)
        if self.instance.pk:
            repetido = repetido.exclude(pk=self.instance.pk)
        if repetido.exists():
            # Aviso, no bloqueo: en un taller hay dos Juan Pérez de verdad. Lo
            # que no puede pasar es darlo de alta dos veces sin enterarse.
            self.add_error(
                None,
                f"Ya hay alguien llamado «{nombre}». Si son dos personas distintas, "
                "añade el apellido para poder distinguirlas.",
            )
        return nombre

    def clean_sueldo_mensual(self):
        sueldo = self.cleaned_data.get("sueldo_mensual")
        if sueldo in (None, ""):
            return Decimal("0")
        if sueldo < 0:
            raise forms.ValidationError("El sueldo no puede ser negativo.")
        return sueldo

    def clean(self):
        limpio = super().clean()
        nacimiento = limpio.get("fecha_nacimiento")
        ingreso = limpio.get("fecha_ingreso")
        hoy = timezone.localdate()

        if nacimiento:
            if nacimiento > hoy:
                self.add_error("fecha_nacimiento", "Esa fecha todavía no ha pasado.")
            elif (hoy - nacimiento).days < 14 * 365:
                # Un dedo de más al teclear el año se ve aquí y no dentro de
                # seis meses en un informe de edades.
                self.add_error("fecha_nacimiento", "¿Seguro? Sale menor de catorce años.")
        if ingreso and ingreso > hoy:
            self.add_error("fecha_ingreso", "Esa fecha todavía no ha pasado.")
        if nacimiento and ingreso and ingreso < nacimiento:
            self.add_error("fecha_ingreso", "Entró a trabajar antes de nacer.")

        puesto = limpio.get("puesto")
        departamento = limpio.get("departamento")
        if puesto and puesto.departamento_id and not departamento:
            # Si el puesto ya dice de qué departamento es, no hay que teclearlo.
            limpio["departamento"] = puesto.departamento
        return limpio

    def save(self, commit=True):
        ficha = super().save(commit=False)
        # `rol` es lo que mira el reparto de trabajo, y sigue siendo una de las
        # cuatro palabras de siempre. El puesto dice a cuál se parece; así se
        # pueden inventar puestos nuevos sin romper las asignaciones.
        puesto = self.cleaned_data.get("puesto")
        if puesto and puesto.rol_de_produccion:
            ficha.rol = puesto.rol_de_produccion
        elif not ficha.rol:
            ficha.rol = "Auxiliar"
        if commit:
            ficha.save()
        return ficha


class CuentaForm(forms.Form):
    """La cuenta con la que esta persona entra al sistema. Opcional.

    Se crea aquí y no en la pantalla de Usuarios porque el enlace entre la
    cuenta y la ficha es justo lo que se olvida cuando son dos pantallas, y sin
    enlace «Mi trabajo» no le enseña sus órdenes a nadie.
    """

    usuario = forms.CharField(
        label="Usuario con el que entra",
        required=False,
        help_text="Déjalo vacío si esta persona no necesita entrar al sistema.",
    )
    contrasena = forms.CharField(
        label="Contraseña",
        required=False,
        widget=forms.PasswordInput(render_value=False),
        help_text="Sólo al crear la cuenta. Para cambiarla después, en Usuarios.",
    )
    pin = forms.CharField(
        label="PIN de la tableta",
        required=False,
        max_length=pines.LARGO,
        help_text=f"{pines.LARGO} dígitos para entrar desde la tableta del piso.",
    )
    grupos = forms.MultipleChoiceField(
        label="Qué puede hacer",
        choices=[],
        required=False,
        widget=forms.CheckboxSelectMultiple(attrs={"form": "form-ficha"}),
    )

    def __init__(self, *args, cuenta=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.cuenta = cuenta
        self.fields["grupos"].choices = [(r["clave"], r["nombre"]) for r in roles.ROLES]
        for nombre, campo in self.fields.items():
            if nombre != "grupos":
                campo.widget.attrs.setdefault("class", "form-control")
        self.fields["pin"].widget.attrs.update(
            {"inputmode": "numeric", "autocomplete": "off", "placeholder": "· · · ·"}
        )
        if cuenta is not None:
            self.fields["usuario"].initial = cuenta.get_username()
            self.fields["usuario"].disabled = True
            self.fields["usuario"].help_text = "Para cambiarlo, en Usuarios."
            self.fields["grupos"].initial = list(cuenta.groups.values_list("name", flat=True))
            self.fields["pin"].initial = pines.de(cuenta)
            self.fields["contrasena"].help_text = "Vacío deja la que tiene."

    def clean_usuario(self):
        nombre = (self.cleaned_data.get("usuario") or "").strip()
        if not nombre or self.cuenta is not None:
            return nombre
        if Usuario.objects.filter(username__iexact=nombre).exists():
            raise forms.ValidationError("Ese usuario ya existe. Elige otro.")
        return nombre

    def clean(self):
        limpio = super().clean()
        usuario = (limpio.get("usuario") or "").strip()
        contrasena = limpio.get("contrasena") or ""
        pin = pines.normalizar(limpio.get("pin") or "")

        if not usuario:
            if contrasena or pin:
                self.add_error(
                    "usuario",
                    "Para poner contraseña o PIN hace falta un usuario con el que entrar.",
                )
            return limpio

        if self.cuenta is None and not contrasena and not pin:
            self.add_error(
                "contrasena",
                "Una cuenta nueva necesita contraseña, o un PIN si es del piso.",
            )
        if contrasena and len(contrasena) < 8:
            self.add_error("contrasena", "Al menos 8 caracteres.")
        return limpio


class DepartamentoForm(forms.ModelForm):
    class Meta:
        model = Departamento
        fields = ["nombre", "descripcion", "activo"]
        labels = {"nombre": "Departamento", "descripcion": "Para qué es", "activo": "En uso"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for nombre, campo in self.fields.items():
            campo.widget.attrs.setdefault(
                "class", "form-check-input" if nombre == "activo" else "form-control"
            )

    def clean_nombre(self):
        nombre = (self.cleaned_data.get("nombre") or "").strip()
        if not nombre:
            raise forms.ValidationError("El nombre hace falta.")
        repetido = Departamento.objects.filter(nombre_normalizado=normalizar(nombre))
        if self.instance.pk:
            repetido = repetido.exclude(pk=self.instance.pk)
        if repetido.exists():
            raise forms.ValidationError("Ya existe ese departamento.")
        return nombre


class PuestoForm(forms.ModelForm):
    class Meta:
        model = Puesto
        fields = ["nombre", "departamento", "rol_de_produccion", "activo"]
        labels = {
            "nombre": "Puesto",
            "departamento": "Departamento",
            "rol_de_produccion": "Equivale a",
            "activo": "En uso",
        }
        help_texts = {
            "rol_de_produccion": (
                "A cuál de los cuatro papeles de producción se parece, para que "
                "el reparto de órdenes siga funcionando. Vacío si no entra en "
                "producción, como administración o almacén."
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["departamento"].queryset = Departamento.objects.filter(activo=True)
        self.fields["departamento"].empty_label = "— Cualquiera —"
        self.fields["departamento"].required = False
        for nombre, campo in self.fields.items():
            if nombre == "activo":
                campo.widget.attrs.setdefault("class", "form-check-input")
            elif isinstance(campo.widget, forms.Select):
                campo.widget.attrs.setdefault("class", "form-select")
            else:
                campo.widget.attrs.setdefault("class", "form-control")

    def clean(self):
        limpio = super().clean()
        nombre = (limpio.get("nombre") or "").strip()
        if not nombre:
            self.add_error("nombre", "El nombre hace falta.")
            return limpio
        repetido = Puesto.objects.filter(
            nombre_normalizado=normalizar(nombre), departamento=limpio.get("departamento")
        )
        if self.instance.pk:
            repetido = repetido.exclude(pk=self.instance.pk)
        if repetido.exists():
            self.add_error("nombre", "Ya existe ese puesto en ese departamento.")
        return limpio


# ---------------------------------------------------------------- pantallas


def _cuenta_de(ficha):
    if not (ficha and ficha.usuario):
        return None
    return Usuario.objects.filter(username=ficha.usuario).first()


def _resumen(fichas):
    """Los números de la cabecera. Se calculan, no se guardan.

    Un total guardado es un total que se queda viejo: alguien da de alta a una
    persona por otra pantalla y la nómina deja de cuadrar sin que nadie se
    entere.
    """
    activas = [f for f in fichas if f.activo]
    return {
        "personas": len(activas),
        "bajas": len(fichas) - len(activas),
        "nomina": sum((f.sueldo_mensual or Decimal("0")) for f in activas),
        "sin_sueldo": len([f for f in activas if not f.sueldo_mensual]),
        "sin_cuenta": len([f for f in activas if not f.usuario]),
    }


@login_required
@solo_administradores
def lista(request):
    departamento = (request.GET.get("departamento") or "").strip()
    puesto = (request.GET.get("puesto") or "").strip()
    ver = (request.GET.get("ver") or "activos").strip()
    q = (request.GET.get("q") or "").strip()

    fichas = Colaborador.objects.select_related("departamento", "puesto", "equipo")
    if ver == "activos":
        fichas = fichas.filter(activo=True)
    elif ver == "bajas":
        fichas = fichas.filter(activo=False)
    if departamento.isdigit():
        fichas = fichas.filter(departamento_id=int(departamento))
    elif departamento == "sin":
        fichas = fichas.filter(departamento__isnull=True)
    if puesto.isdigit():
        fichas = fichas.filter(puesto_id=int(puesto))
    if q:
        fichas = fichas.filter(Q(nombre__icontains=q) | Q(usuario__icontains=q))
    fichas = list(fichas.order_by("-activo", "nombre"))

    # Para el resumen se miran todas, no las filtradas: si no, filtrar por un
    # departamento haría creer que la nómina del taller es la de ese
    # departamento.
    todas = list(Colaborador.objects.only("activo", "sueldo_mensual", "usuario"))

    por_departamento = list(
        Departamento.objects.filter(activo=True)
        .annotate(
            gente=Count("colaboradores", filter=Q(colaboradores__activo=True)),
            nomina=Sum("colaboradores__sueldo_mensual", filter=Q(colaboradores__activo=True)),
        )
        .order_by("nombre")
    )
    huerfanos = Colaborador.objects.filter(activo=True, departamento__isnull=True).count()

    return render(
        request,
        "personal/lista.html",
        {
            "fichas": fichas,
            "resumen": _resumen(todas),
            "por_departamento": por_departamento,
            "huerfanos": huerfanos,
            "departamentos": Departamento.objects.filter(activo=True),
            "puestos": Puesto.objects.filter(activo=True).select_related("departamento"),
            "filtros": {"departamento": departamento, "puesto": puesto, "ver": ver, "q": q},
        },
    )


def _pantalla_de_ficha(request, ficha, form, cuenta_form):
    return render(
        request,
        "personal/ficha.html",
        {
            "ficha": ficha,
            "form": form,
            "cuenta_form": cuenta_form,
            "cuenta": _cuenta_de(ficha),
            "roles": roles.ROLES,
            "hay_departamentos": Departamento.objects.filter(activo=True).exists(),
            "hay_puestos": Puesto.objects.filter(activo=True).exists(),
        },
    )


def _guardar_cuenta(request, ficha, cuenta_form):
    """Crea o actualiza la cuenta de esta persona y la enlaza con su ficha.

    Reutiliza los ayudantes de la pantalla de Usuarios en vez de repetirlos:
    lo del PIN, en concreto, tiene un orden que importa —los grupos primero,
    porque quién puede tener PIN depende del rol— y ya está resuelto allí.
    """
    nombre = (cuenta_form.cleaned_data.get("usuario") or "").strip()
    if not nombre:
        return

    cuenta = cuenta_form.cuenta
    nueva = cuenta is None
    if nueva:
        cuenta = Usuario.objects.create_user(username=nombre)

    contrasena = cuenta_form.cleaned_data.get("contrasena") or ""
    if contrasena:
        cuenta.set_password(contrasena)
    cuenta.first_name = ficha.nombre[:150]
    cuenta.is_active = ficha.activo
    cuenta.save()

    _aplicar_grupos(cuenta, cuenta_form.cleaned_data.get("grupos") or [])
    _guardar_enlace(cuenta, ficha)
    _guardar_pin(request, cuenta, cuenta_form.cleaned_data.get("pin") or "")

    if nueva:
        messages.success(request, f"Cuenta «{nombre}» creada para {ficha.nombre}.")


@login_required
@solo_administradores
@require_http_methods(["GET", "POST"])
def alta(request):
    if request.method == "POST":
        form = FichaForm(request.POST)
        cuenta_form = CuentaForm(request.POST)
        if form.is_valid() and cuenta_form.is_valid():
            with transaction.atomic(using=BASE):
                ficha = form.save()
            _guardar_cuenta(request, ficha, cuenta_form)
            messages.success(request, f"{ficha.nombre} dado de alta.")
            return redirect("personal:lista")
    else:
        form = FichaForm(initial={"fecha_ingreso": timezone.localdate(), "activo": True})
        cuenta_form = CuentaForm()
    return _pantalla_de_ficha(request, None, form, cuenta_form)


@login_required
@solo_administradores
@require_http_methods(["GET", "POST"])
def editar(request, pk: int):
    ficha = get_object_or_404(Colaborador, pk=pk)
    cuenta = _cuenta_de(ficha)
    if request.method == "POST":
        form = FichaForm(request.POST, instance=ficha)
        cuenta_form = CuentaForm(request.POST, cuenta=cuenta)
        if form.is_valid() and cuenta_form.is_valid():
            with transaction.atomic(using=BASE):
                ficha = form.save()
            _guardar_cuenta(request, ficha, cuenta_form)
            messages.success(request, f"{ficha.nombre} actualizado.")
            return redirect("personal:lista")
    else:
        form = FichaForm(instance=ficha)
        cuenta_form = CuentaForm(cuenta=cuenta)
    return _pantalla_de_ficha(request, ficha, form, cuenta_form)


@login_required
@solo_administradores
@require_POST
def dar_de_baja(request, pk: int):
    """Se apaga, no se borra.

    Sus asignaciones, sus firmas y su rendimiento quedan en el historial. Si se
    borrara la ficha, todo eso se quedaría sin dueño y el historial dejaría de
    poder explicarse.
    """
    ficha = get_object_or_404(Colaborador, pk=pk)
    ficha.activo = not ficha.activo
    ficha.save(update_fields=["activo", "actualizado_en"])

    cuenta = _cuenta_de(ficha)
    if cuenta is not None:
        cuenta.is_active = ficha.activo
        cuenta.save(update_fields=["is_active"])
        if not ficha.activo:
            pines.quitar(cuenta)

    if ficha.activo:
        messages.success(request, f"{ficha.nombre} vuelve a estar activo.")
    else:
        messages.info(
            request,
            f"{ficha.nombre} queda dado de baja. Su historial se conserva"
            + (", y su cuenta ya no puede entrar." if cuenta else "."),
        )
    return redirect("personal:lista")


@login_required
@solo_administradores
@require_http_methods(["GET", "POST"])
def organizacion(request):
    """Departamentos y puestos, en la misma pantalla.

    Juntos y no en dos sitios porque un puesto sin departamento al que
    colgarse no sirve de nada, y se dan de alta seguidos.
    """
    editar_departamento = Departamento.objects.filter(
        pk=int(request.GET.get("departamento") or 0)
    ).first()
    editar_puesto = Puesto.objects.filter(pk=int(request.GET.get("puesto") or 0)).first()

    departamento_form = DepartamentoForm(instance=editar_departamento)
    puesto_form = PuestoForm(instance=editar_puesto)

    if request.method == "POST":
        que = (request.POST.get("que") or "").strip()
        if que == "departamento":
            pk = int(request.POST.get("id") or 0)
            objetivo = Departamento.objects.filter(pk=pk).first()
            departamento_form = DepartamentoForm(request.POST, instance=objetivo)
            if departamento_form.is_valid():
                departamento_form.save()
                messages.success(request, "Departamento guardado.")
                return redirect("personal:organizacion")
        elif que == "puesto":
            pk = int(request.POST.get("id") or 0)
            objetivo = Puesto.objects.filter(pk=pk).first()
            puesto_form = PuestoForm(request.POST, instance=objetivo)
            if puesto_form.is_valid():
                puesto_form.save()
                messages.success(request, "Puesto guardado.")
                return redirect("personal:organizacion")

    return render(
        request,
        "personal/organizacion.html",
        {
            "departamento_form": departamento_form,
            "puesto_form": puesto_form,
            "editar_departamento": editar_departamento,
            "editar_puesto": editar_puesto,
            "departamentos": Departamento.objects.annotate(
                gente=Count("colaboradores", filter=Q(colaboradores__activo=True))
            ),
            "puestos": Puesto.objects.select_related("departamento").annotate(
                gente=Count("colaboradores", filter=Q(colaboradores__activo=True))
            ),
        },
    )
