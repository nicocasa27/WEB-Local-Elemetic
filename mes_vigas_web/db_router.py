class MESRouter:
    #: `nucleo` va a la misma base que el resto del negocio. Tiene que estar
    #: aquí desde la primera migración: si se creara en `default` no podría
    #: tener claves foráneas hacia `catalogos.Colaborador` ni `Maquina`, que
    #: es justo lo que se está arreglando.
    route_app_labels = {"produccion", "catalogos", "nucleo", "inventario"}

    def db_for_read(self, model, **hints):
        if model._meta.app_label in self.route_app_labels:
            return "mes"
        return None

    def db_for_write(self, model, **hints):
        if model._meta.app_label in self.route_app_labels:
            return "mes"
        return None

    def allow_relation(self, obj1, obj2, **hints):
        if obj1._meta.app_label in self.route_app_labels or obj2._meta.app_label in self.route_app_labels:
            return True
        return None

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        if app_label in self.route_app_labels:
            return db == "mes"
        return db == "default"
