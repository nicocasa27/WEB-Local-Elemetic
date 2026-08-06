"""Campos de formulario que se repiten por todo el sistema."""

from django import forms


class CampoDeFecha(forms.DateInput):
    """Un `<input type="date">` que **sí** enseña la fecha que trae.

    Estaba puesto a mano en catorce sitios como
    `forms.DateInput(attrs={"type": "date"})`, y en los catorce no funcionaba:
    el sistema está en `es-mx`, así que Django pintaba `value="06/08/2026"`,
    y un campo de fecha del navegador **sólo** entiende `2026-08-06`. Al no
    reconocer el formato, el navegador tira el valor y deja el campo vacío.

    El efecto era que ninguna fecha llegaba puesta. Al dar de alta un pedido la
    fecha de compromiso salía en blanco aunque la vista la pusiera en hoy, y al
    editar cualquier cosa la fecha guardada desaparecía de la pantalla: si no
    se volvía a teclear, se guardaba vacía o daba error de campo obligatorio.
    Nadie lo relacionaba con el idioma.

    El navegador **enseña** la fecha en el formato de quien la mira -en México
    sigue viéndose dd/mm/aaaa-, así que esto no cambia nada de lo que se ve.
    Sólo arregla lo que viaja por dentro.
    """

    input_type = "date"

    def __init__(self, attrs=None, format=None):
        atributos = {"class": "form-control"}
        atributos.update(attrs or {})
        atributos["type"] = "date"
        super().__init__(attrs=atributos, format="%Y-%m-%d")
