from django.conf import settings


class MESRouter:
    """Reparte los modelos entre las bases, y con una sola base se aparta.

    **Con dos bases (como está hoy).** `default` es SQLite y guarda
    autenticación y sesiones; `mes` es PostgreSQL y guarda el negocio.

    **Con una sola base (`MES_UNA_SOLA_BASE=1`).** Los dos alias apuntan al
    mismo PostgreSQL, así que repartir deja de tener sentido y `allow_migrate`
    cambia de forma. Eso no es un detalle: es **la trampa que rompió el intento
    anterior de unificar**, documentada en DESPLIEGUE.md.

    Cuando el router dice que una aplicación no va a cierta base, Django no
    crea las tablas pero **sí anota la migración como aplicada**. Con dos bases
    distintas eso pasaba desapercibido porque cada una tenía su propia
    `django_migrations`. Con una sola, las dos la comparten: `migrate` sobre
    `default` marcaría las 66 migraciones del negocio como hechas sin crear una
    sola tabla, y el `migrate --database=mes` siguiente no haría nada porque
    creería que ya está.

    La salida es que con una sola base **todo se migra una vez, por `default`**,
    y `mes` queda como un alias del mismo sitio para que las 346 llamadas
    `.using("mes")` sigan funcionando sin tocar ninguna.
    """

    #: `nucleo` va a la misma base que el resto del negocio. Tiene que estar
    #: aquí desde la primera migración: si se creara en `default` no podría
    #: tener claves foráneas hacia `catalogos.Colaborador` ni `Maquina`, que
    #: es justo lo que se está arreglando.
    route_app_labels = {"produccion", "catalogos", "nucleo", "inventario", "costeo", "personal"}

    @property
    def una_sola_base(self):
        return bool(getattr(settings, "UNA_SOLA_BASE", False))

    def db_for_read(self, model, **hints):
        if self.una_sola_base:
            return None
        if model._meta.app_label in self.route_app_labels:
            return "mes"
        return None

    def db_for_write(self, model, **hints):
        if self.una_sola_base:
            return None
        if model._meta.app_label in self.route_app_labels:
            return "mes"
        return None

    def allow_relation(self, obj1, obj2, **hints):
        # Con una sola base cualquier relación es legítima, incluidas las que
        # hoy no se pueden declarar: las de un registro con quien lo hizo.
        if self.una_sola_base:
            return True
        if obj1._meta.app_label in self.route_app_labels or obj2._meta.app_label in self.route_app_labels:
            return True
        return None

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        if self.una_sola_base:
            # Todo por `default`, una sola vez. Ver el docstring.
            return db == "default"
        if app_label in self.route_app_labels:
            return db == "mes"
        return db == "default"
