from django import forms

from catalogos.models import Proyecto

from .models import ESTADOS, Viga

PRIORIDAD_CHOICES = [(i, str(i)) for i in range(1, 6)]


class VigaForm(forms.ModelForm):
    class Meta:
        model = Viga
        fields = [
            "codigo_viga",
            "pieza_no",
            "total_piezas",
            "proyecto",
            "descripcion",
            "fecha_compromiso",
            "estado",
            "observaciones",
            "prioridad",
            "peso_kg",
        ]
        widgets = {
            "fecha_compromiso": forms.DateInput(attrs={"type": "date"}),
            "codigo_viga": forms.TextInput(),
            "descripcion": forms.TextInput(),
            "observaciones": forms.Textarea(attrs={"rows": 3}),
        }

    estado = forms.ChoiceField(choices=[(s, s) for s in ESTADOS])
    proyecto = forms.ChoiceField(choices=[])
    prioridad = forms.TypedChoiceField(choices=PRIORIDAD_CHOICES, coerce=int)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        proyectos = Proyecto.objects.filter(activo=True).order_by("nombre")
        self.fields["proyecto"].choices = [(p.nombre_normalizado, p.nombre) for p in proyectos]
        self.fields["descripcion"].label = "Perfil"
        if self.instance and getattr(self.instance, "proyecto", None):
            current_norm = str(self.instance.proyecto).strip().upper()
            self.initial["proyecto"] = current_norm
            active_norms = {norm for norm, _label in self.fields["proyecto"].choices}
            if current_norm and current_norm not in active_norms:
                p = Proyecto.objects.filter(nombre_normalizado=current_norm).first()
                label = (p.nombre if p else current_norm) + " (inactivo)"
                self.fields["proyecto"].choices = [(current_norm, label), *self.fields["proyecto"].choices]
        for name, field in self.fields.items():
            if isinstance(field.widget, forms.Select):
                css = "form-select"
            elif isinstance(field.widget, forms.Textarea):
                css = "form-control"
            else:
                css = "form-control"
            field.widget.attrs.setdefault("class", css)

    def clean_proyecto(self):
        value = (self.cleaned_data.get("proyecto") or "").strip()
        if not value:
            raise forms.ValidationError("Debes seleccionar un proyecto.")
        proyecto, _created = Proyecto.objects.get_or_create(
            nombre_normalizado=value.upper(),
            defaults={"nombre": value.upper(), "activo": True},
        )
        return proyecto.nombre


class VigaBatchCreateForm(forms.ModelForm):
    cantidad_piezas = forms.IntegerField(min_value=1, initial=1)
    estado = forms.ChoiceField(choices=[(s, s) for s in ESTADOS])
    proyecto = forms.ChoiceField(choices=[])
    prioridad = forms.TypedChoiceField(choices=PRIORIDAD_CHOICES, coerce=int, initial=1)

    class Meta:
        model = Viga
        fields = [
            "codigo_viga",
            "proyecto",
            "descripcion",
            "fecha_compromiso",
            "estado",
            "observaciones",
            "prioridad",
            "peso_kg",
        ]
        widgets = {
            "fecha_compromiso": forms.DateInput(attrs={"type": "date"}),
            "codigo_viga": forms.TextInput(),
            "descripcion": forms.TextInput(),
            "observaciones": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        proyectos = Proyecto.objects.filter(activo=True).order_by("nombre")
        self.fields["proyecto"].choices = [("", "Seleccionar…"), *[(p.nombre_normalizado, p.nombre) for p in proyectos]]
        self.fields["descripcion"].label = "Perfil"
        for name, field in self.fields.items():
            if isinstance(field.widget, forms.Select):
                css = "form-select"
            elif isinstance(field.widget, forms.Textarea):
                css = "form-control"
            else:
                css = "form-control"
            field.widget.attrs.setdefault("class", css)
        self.fields["cantidad_piezas"].widget.attrs.setdefault("class", "form-control")

    def clean_proyecto(self):
        value = (self.cleaned_data.get("proyecto") or "").strip()
        if not value:
            raise forms.ValidationError("Debes seleccionar un proyecto.")
        proyecto, _created = Proyecto.objects.get_or_create(
            nombre_normalizado=value.upper(),
            defaults={"nombre": value.upper(), "activo": True},
        )
        return proyecto.nombre


class StatusChangeForm(forms.Form):
    estado_nuevo = forms.ChoiceField(choices=[(s, s) for s in ESTADOS])
    fecha_operacion = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date", "required": "required"}),
    )
    comentario = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}))


class VigaImportUploadForm(forms.Form):
    archivo = forms.FileField()
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if isinstance(field.widget, forms.Select):
                css = "form-select"
            elif isinstance(field.widget, forms.Textarea):
                css = "form-control"
            else:
                css = "form-control"
            field.widget.attrs.setdefault("class", css)
