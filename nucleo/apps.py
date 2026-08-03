from django.apps import AppConfig


class NucleoConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "nucleo"
    verbose_name = "Núcleo de producción"

    def ready(self):
        # Las señales de escritura doble se conectan siempre; no hacen nada
        # mientras las líneas estén apagadas, que es como están por omisión.
        # Conectarlas aquí y no condicionalmente evita que encender una
        # bandera exija además reiniciar con otra configuración.
        from nucleo import signals

        signals.conectar()
