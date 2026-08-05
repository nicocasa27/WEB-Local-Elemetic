"""Alta y modificación de usuarios desde el propio sistema.

Hasta ahora no había pantalla: crear una cuenta significaba entrar al admin de
Django, buscar entre once grupos con nombre técnico y adivinar cuál tocaba. En
la práctica eso quería decir que **nadie del piso tenía cuenta**: los once
usuarios del sistema son todos de oficina, y la pantalla «Mi trabajo» del
celular no la podía abrir ningún cortador, soldador ni pintor.

Aquí se hace en castellano, con los roles explicados, y con lo que faltaba:
enlazar la cuenta con la ficha del colaborador. Sin ese enlace el sistema sabe
que entró «jperez» pero no que jperez es Juan Pérez del equipo de soldadura, y
entonces «Mi trabajo» no puede enseñarle sus órdenes.

Sobre borrar: **no se borra a nadie**. Una cuenta se apaga. Si se borrara, los
movimientos que esa persona registró se quedarían sin autor y el historial
dejaría de poder explicarse.
"""

from django import forms
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import Group
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from catalogos.models import Colaborador
from catalogos.management.commands.crear_admin import (
    CONTRASENA_DE_FABRICA,
    USUARIO as USUARIO_ADMIN,
    usa_la_de_fabrica,
)
from core import roles

Usuario = get_user_model()

BASE = "mes"

#: Longitud mínima de una contraseña nueva. Corta a propósito: en el piso se
#: teclea con guantes, y una regla imposible acaba en la contraseña escrita en
#: un papel pegado al monitor.
MINIMO_CONTRASENA = 8


solo_administradores = user_passes_test(
    roles.puede_administrar_usuarios, login_url="login"
)


# ------------------------------------------------------------- formularios


class UsuarioForm(forms.ModelForm):
    """Alta y edición. La contraseña se trata aparte."""

    grupos = forms.MultipleChoiceField(
        label="Qué puede hacer",
        choices=[],
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )
    colaborador = forms.ModelChoiceField(
        label="Ficha de la persona",
        queryset=Colaborador.objects.none(),
        required=False,
        empty_label="— Sin enlazar —",
        help_text=(
            "Enlaza la cuenta con su ficha del taller. Sin esto, «Mi trabajo» "
            "no le puede enseñar sus órdenes."
        ),
    )

    class Meta:
        model = Usuario
        fields = ["username", "first_name", "last_name", "email", "is_active"]
        labels = {
            "username": "Usuario con el que entra",
            "first_name": "Nombre",
            "last_name": "Apellidos",
            "email": "Correo (opcional)",
            "is_active": "Puede entrar",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["grupos"].choices = [
            (r["clave"], r["nombre"]) for r in roles.ROLES
        ]
        self.fields["colaborador"].queryset = (
            Colaborador.objects.using(BASE).filter(activo=True).order_by("nombre")
        )
        for nombre, campo in self.fields.items():
            if nombre in {"grupos", "is_active"}:
                continue
            campo.widget.attrs.setdefault("class", "form-control")
            campo.widget.attrs.setdefault("id", f"campo-{nombre}")
        self.fields["colaborador"].widget.attrs["class"] = "form-select"
        self.fields["is_active"].widget.attrs.setdefault("class", "form-check-input")
        self.fields["is_active"].widget.attrs.setdefault("id", "campo-is_active")

        if self.instance.pk:
            self.fields["grupos"].initial = list(
                self.instance.groups.values_list("name", flat=True)
            )
            enlazado = (
                Colaborador.objects.using(BASE)
                .filter(usuario=self.instance.username)
                .first()
            )
            self.fields["colaborador"].initial = enlazado

    def clean_username(self):
        nombre = (self.cleaned_data["username"] or "").strip()
        if self.instance.pk and self.instance.username == USUARIO_ADMIN and nombre != USUARIO_ADMIN:
            # Si se le cambia el nombre al administrador fijo, `crear_admin`
            # crearía otro la próxima vez y habría dos.
            raise forms.ValidationError(
                "Al administrador fijo no se le puede cambiar el usuario."
            )
        return nombre


class ContrasenaForm(forms.Form):
    contrasena = forms.CharField(
        label="Contraseña nueva",
        widget=forms.PasswordInput(attrs={"class": "form-control", "id": "campo-contrasena"}),
        min_length=MINIMO_CONTRASENA,
        help_text=f"Mínimo {MINIMO_CONTRASENA} caracteres.",
    )
    repetida = forms.CharField(
        label="Repetir",
        widget=forms.PasswordInput(attrs={"class": "form-control", "id": "campo-repetida"}),
    )

    def clean(self):
        datos = super().clean()
        if datos.get("contrasena") and datos.get("contrasena") != datos.get("repetida"):
            raise forms.ValidationError("Las dos contraseñas no coinciden.")
        return datos


# ------------------------------------------------------------------ vistas


def _guardar_enlace(usuario, colaborador):
    """Apunta la ficha del colaborador a esta cuenta.

    Se limpia primero cualquier otra ficha que apuntara aquí: una cuenta es de
    una persona, y dos fichas con el mismo usuario harían que «Mi trabajo»
    enseñara las órdenes de otro.
    """
    Colaborador.objects.using(BASE).filter(usuario=usuario.username).exclude(
        pk=getattr(colaborador, "pk", None)
    ).update(usuario="")
    if colaborador is not None:
        colaborador.usuario = usuario.username
        colaborador.save(using=BASE, update_fields=["usuario"])


def _aplicar_grupos(usuario, claves):
    """Pone los roles marcados, creando los que falten en la base.

    `groups.set()` con un `filter` descarta en silencio los grupos que no
    existen. Un rol nuevo —«pintura» fue el último— no existe en la base del
    taller hasta que alguien corre un comando, así que sin esto un
    administrador lo marcaba en la pantalla, guardaba sin ningún error, y el
    rol no se aplicaba. El único síntoma sería que a esa persona el sistema
    no la deja hacer su trabajo, tres días después y sin relación aparente.

    `asegurar_grupos` es idempotente y no borra ninguno.
    """
    roles.asegurar_grupos()
    usuario.groups.set(Group.objects.filter(name__in=claves))
    # `is_staff` abre el admin de Django, que enseña las tablas en crudo. Se
    # deja sólo a quien administra usuarios.
    usuario.is_staff = bool(set(claves) & roles.QUE_ADMINISTRAN)
    usuario.save(update_fields=["is_staff"])


@login_required
@solo_administradores
def lista(request):
    cuentas = Usuario.objects.all().prefetch_related("groups").order_by(
        "-is_active", "username"
    )
    enlaces = {
        c.usuario: c
        for c in Colaborador.objects.using(BASE).exclude(usuario="")
    }

    filas = []
    for cuenta in cuentas:
        grupos = list(cuenta.groups.values_list("name", flat=True))
        filas.append({
            "cuenta": cuenta,
            "papeles": [roles.por_clave(g) or {"nombre": g} for g in grupos],
            "colaborador": enlaces.get(cuenta.username),
            "es_de_piso": bool(set(grupos) & roles.DE_PISO),
            "administra": bool(set(grupos) & roles.QUE_ADMINISTRAN) or cuenta.is_superuser,
        })

    # Cuánta gente del taller sigue sin cuenta. Es el número que explica por
    # qué «Mi trabajo» no se usa.
    sin_cuenta = (
        Colaborador.objects.using(BASE).filter(activo=True, usuario="").count()
    )

    return render(request, "catalogos/usuarios.html", {
        "filas": filas,
        "sin_cuenta": sin_cuenta,
        "roles": roles.ROLES,
        "aviso_contrasena": usa_la_de_fabrica(),
        "usuario_admin": USUARIO_ADMIN,
        "contrasena_de_fabrica": CONTRASENA_DE_FABRICA,
    })


@login_required
@solo_administradores
@transaction.atomic
def crear(request):
    if request.method == "POST":
        form = UsuarioForm(request.POST)
        clave = ContrasenaForm(request.POST)
        if form.is_valid() and clave.is_valid():
            usuario = form.save(commit=False)
            usuario.set_password(clave.cleaned_data["contrasena"])
            usuario.save()
            _aplicar_grupos(usuario, form.cleaned_data["grupos"])
            _guardar_enlace(usuario, form.cleaned_data["colaborador"])
            messages.success(request, f"Cuenta de {usuario.username} creada.")
            return redirect("catalogos:usuarios")
    else:
        form = UsuarioForm(initial={"is_active": True})
        clave = ContrasenaForm()

    return render(request, "catalogos/usuario_editar.html", {
        "form": form,
        "clave": clave,
        "roles": roles.ROLES,
        "es_nuevo": True,
    })


@login_required
@solo_administradores
@transaction.atomic
def editar(request, pk: int):
    usuario = get_object_or_404(Usuario, pk=pk)
    if request.method == "POST":
        form = UsuarioForm(request.POST, instance=usuario)
        if form.is_valid():
            form.save()
            _aplicar_grupos(usuario, form.cleaned_data["grupos"])
            _guardar_enlace(usuario, form.cleaned_data["colaborador"])
            messages.success(request, f"Cuenta de {usuario.username} actualizada.")
            return redirect("catalogos:usuarios")
    else:
        form = UsuarioForm(instance=usuario)

    return render(request, "catalogos/usuario_editar.html", {
        "form": form,
        "clave": ContrasenaForm(),
        "roles": roles.ROLES,
        "usuario": usuario,
        "es_nuevo": False,
    })


@login_required
@solo_administradores
@require_POST
def cambiar_contrasena(request, pk: int):
    usuario = get_object_or_404(Usuario, pk=pk)
    clave = ContrasenaForm(request.POST)
    if clave.is_valid():
        usuario.set_password(clave.cleaned_data["contrasena"])
        usuario.save()
        messages.success(request, f"Contraseña de {usuario.username} cambiada.")
    else:
        for error in clave.errors.values():
            messages.error(request, "; ".join(error))
    return redirect("catalogos:usuario_editar", pk=pk)


@login_required
@solo_administradores
@require_POST
def apagar(request, pk: int):
    """Apaga o vuelve a encender una cuenta. Nunca la borra.

    Borrarla dejaría sin autor los movimientos que esa persona registró, y el
    historial dejaría de poder explicarse.
    """
    usuario = get_object_or_404(Usuario, pk=pk)

    if usuario.username == USUARIO_ADMIN:
        messages.error(
            request, "El administrador fijo no se puede apagar: es la entrada de respaldo."
        )
        return redirect("catalogos:usuarios")

    if usuario.pk == request.user.pk:
        messages.error(request, "No puedes apagar tu propia cuenta.")
        return redirect("catalogos:usuarios")

    usuario.is_active = not usuario.is_active
    usuario.save(update_fields=["is_active"])
    messages.success(
        request,
        f"Cuenta de {usuario.username} "
        + ("encendida." if usuario.is_active else "apagada."),
    )
    return redirect("catalogos:usuarios")
