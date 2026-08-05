"""Entrar al sistema con cuatro dígitos.

En el piso hay gente que no teclea un correo y una contraseña de ocho
caracteres con guantes puestos, de pie, delante de una tableta compartida. En
la práctica eso significaba una de dos cosas: o no entraban —y el avance se
apuntaba en papel para que alguien lo capturara por la tarde— o alguien dejaba
una sesión abierta y todo el turno quedaba registrado a nombre de esa persona.
Las dos rompen lo mismo: **el sistema deja de saber quién hizo qué**, que es
justo el dato que se usa para medir el rendimiento.

Un PIN de cuatro dígitos arregla el acceso sin pedirle a nadie que recuerde
una contraseña.

Por qué el PIN se guarda tal cual y no cifrado
----------------------------------------------

Porque **no es un secreto, es un gafete**. El taller lo pidió así de forma
explícita: que otro compañero se sepa el PIN no importa, porque a nadie le
conviene cortar material a nombre de otro —el rendimiento que sube es el del
otro—. Lo que el PIN contesta es «¿quién está delante de la tableta?», no
«¿tiene esta persona permiso para entrar?».

Y guardarlo con un resumen criptográfico costaría las dos cosas que sí hacen
falta:

- **La unicidad.** Un resumen con sal no se puede comparar entre filas, así
  que la base no podría impedir que dos personas eligieran el 1234. Y el taller
  lo pidió: si un PIN está ocupado, que no lo pueda poner otro.
- **La búsqueda.** Con resumen habría que probar el PIN tecleado contra cada
  una de las cuentas del taller, una por una, en cada intento.

La protección real no está en esconder los dígitos: está en que **un PIN sólo
abre cuentas de piso**. Ver `servicios.puede_tener_pin`. Cuatro dígitos son
diez mil combinaciones, y eso no puede ser lo único que separe a cualquiera de
la cuenta de administración.
"""

from django.conf import settings
from django.db import models


class Pin(models.Model):
    """Los cuatro dígitos con los que una persona del piso entra.

    Vive en la base `default`, junto a la autenticación, porque apunta a
    `User` con una clave foránea de verdad y Django no admite claves foráneas
    entre bases. El día que se unifiquen las dos bases, esta tabla se muda con
    `auth` sin tocar nada.
    """

    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="pin",
    )
    #: Exactamente cuatro dígitos, únicos en todo el taller. La unicidad la
    #: impone la base y no sólo el formulario: dos personas con el mismo PIN
    #: harían que el trabajo se registrara a nombre de cualquiera de las dos,
    #: y el error no daría ningún síntoma hasta que alguien revisara el
    #: rendimiento del mes.
    digitos = models.CharField(max_length=8, unique=True)
    #: Quién lo puso. Un PIN lo asigna quien administra usuarios, no su dueño,
    #: y conviene poder preguntar quién.
    actualizado_por = models.CharField(max_length=150, blank=True, default="")
    actualizado_en = models.DateTimeField(auto_now=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "PIN de acceso"
        verbose_name_plural = "PINes de acceso"
        ordering = ["digitos"]

    def __str__(self):
        return f"{self.digitos} · {self.usuario.get_username()}"
