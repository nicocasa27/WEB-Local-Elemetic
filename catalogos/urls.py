from django.urls import path

from . import (
    cuadrillas,
    despacho,
    proyecto,
    terminado,
    trazabilidad,
    usuarios,
    views,
)

app_name = "catalogos"

urlpatterns = [
    path("proyectos/", views.proyectos, name="proyectos"),
    # Qué lleva el proyecto y cómo va, de las cuatro líneas. Lo requerido se
    # apunta aquí porque no se puede deducir de ningún lado: sin ello, «faltan
    # dieciocho» no es una resta, es una adivinanza.
    path("proyectos/<int:pk>/", proyecto.detalle, name="proyecto_detalle"),
    path(
        "proyectos/<int:pk>/requerimiento/",
        proyecto.requerimiento_crear,
        name="proyecto_requerimiento_crear",
    ),
    path(
        "proyectos/<int:pk>/requerimiento/<int:requerimiento>/borrar/",
        proyecto.requerimiento_borrar,
        name="proyecto_requerimiento_borrar",
    ),
    path("equipos/", views.equipos, name="equipos"),
    path("equipos/<int:pk>/toggle/", views.equipo_toggle, name="equipo_toggle"),
    path("equipos/<int:pk>/eliminar/", views.equipo_delete, name="equipo_delete"),
    path("colaboradores/<int:pk>/toggle/", views.colaborador_toggle, name="colaborador_toggle"),
    path("colaboradores/<int:pk>/editar/", views.colaborador_editar, name="colaborador_editar"),
    path("colaboradores/<int:pk>/eliminar/", views.colaborador_delete, name="colaborador_delete"),
    path("maquinas/", views.maquinas, name="maquinas"),
    path("maquinas/<int:pk>/toggle/", views.maquina_toggle, name="maquina_toggle"),
    path("maquinas/<int:pk>/editar/", views.maquina_editar, name="maquina_editar"),
    path("maquinas/<int:pk>/eliminar/", views.maquina_delete, name="maquina_delete"),
    path("robotica/", views.robotica, name="robotica"),
    path("robotica/ordenes/", views.robotica_ordenes, name="robotica_ordenes"),
    path("robotica/ordenes/<int:pk>/", views.robotica_orden_detalle, name="robotica_orden_detalle"),
    path("robotica/robots/<int:pk>/editar/", views.robot_editar, name="robot_editar"),
    path("robotica/piezas/<int:pk>/editar/", views.robot_pieza_editar, name="robot_pieza_editar"),
    path("herreria/", views.herreria, name="herreria"),
    path("herreria/control/", views.herreria_control, name="herreria_control"),
    path("herreria/nueva/", views.herreria_create, name="herreria_create"),
    path("herreria/<int:pk>/editar/", views.herreria_update, name="herreria_update"),
    path("herreria/<int:pk>/eliminar/", views.herreria_delete, name="herreria_delete"),
    path("herreria/<int:pk>/meta/json/", views.herreria_update_meta_json, name="herreria_update_meta_json"),
    path("herreria/<int:pk>/avance/json/", views.herreria_update_avance_json, name="herreria_update_avance_json"),
    path("herreria/<int:pk>/revertir-cierre/", views.herreria_revertir_cierre, name="herreria_revertir_cierre"),
    path("herreria/<int:pk>/asignaciones/", views.herreria_asignaciones, name="herreria_asignaciones"),
    path("herreria/<int:pk>/estado/json/", views.herreria_change_status_json, name="herreria_change_status_json"),
    path("herreria/<int:pk>/enviar/", views.herreria_enviar, name="herreria_enviar"),
    path("herreria/<int:pk>/regresar-produccion/", views.herreria_regresar_produccion, name="herreria_regresar_produccion"),
    path("herreria/<int:pk>/decote/eliminar/", views.herreria_delete_decote, name="herreria_delete_decote"),
    path("herreria/decote/eliminar-todo/", views.herreria_delete_decote_all, name="herreria_delete_decote_all"),
    path("herreria/acuse/crear/", views.herreria_acuse_create, name="herreria_acuse_create"),
    path("herreria/acuse/<int:pk>/", views.herreria_acuse_print, name="herreria_acuse_print"),
    path("herreria/catalogo/", views.herreria_catalogo, name="herreria_catalogo"),
    path("herreria/catalogo/piezas/<int:pk>/editar/", views.herreria_pieza_editar, name="herreria_pieza_editar"),
    path("herreria/ordenes/", views.herreria_ordenes, name="herreria_ordenes"),
    path("herreria/ordenes/<int:pk>/", views.herreria_orden_detalle, name="herreria_orden_detalle"),
    path("herreria/ordenes/<int:pk>/estado/json/", views.herreria_change_status_json, name="herreria_change_status_json_old"),
    path("pedidos/ordenes/", views.pedidos_ordenes, name="pedidos_ordenes"),
    path("pedidos/ordenes/<int:pk>/editar/", views.pedidos_orden_editar, name="pedidos_orden_editar"),
    path("pedidos/ordenes/<int:pk>/cancelar/", views.pedidos_orden_cancelar, name="pedidos_orden_cancelar"),
    path("pedidos/ordenes/<int:pk>/eliminar/", views.pedidos_orden_eliminar, name="pedidos_orden_eliminar"),
    path("pedidos/ordenes/<int:pk>/expediente.zip", views.pedidos_expediente_zip, name="pedidos_expediente_zip"),
    path("pedidos/logistica/", views.pedidos_logistica, name="pedidos_logistica"),
    path("pedidos/logistica/corta/", views.logistica_corta, name="logistica_corta"),
    path("pedidos/logistica/corta/<int:pk>/expediente.zip", views.corta_expediente_zip, name="corta_expediente_zip"),
    path("corte-laser/", views.corte_laser, name="corte_laser"),
    path("corte-laser/control/", views.corte_laser_control, name="corte_laser_control"),
    path("corte-laser/nueva/", views.corte_laser_create, name="corte_laser_create"),
    path("corte-laser/<int:pk>/editar/", views.corte_laser_update, name="corte_laser_update"),
    path("corte-laser/<int:pk>/eliminar/", views.corte_laser_delete, name="corte_laser_delete"),
    path("corte-laser/<int:pk>/meta/json/", views.corte_laser_update_meta_json, name="corte_laser_update_meta_json"),
    path("corte-laser/<int:pk>/avance/json/", views.corte_laser_update_avance_json, name="corte_laser_update_avance_json"),
    path("corte-laser/<int:pk>/revertir-cierre/", views.corte_laser_revertir_cierre, name="corte_laser_revertir_cierre"),
    path("corte-laser/<int:pk>/asignaciones/", views.corte_laser_asignaciones, name="corte_laser_asignaciones"),
    path("corte-laser/<int:pk>/estado/json/", views.corte_laser_change_status_json, name="corte_laser_change_status_json"),
    path("corte-laser/<int:pk>/enviar/", views.corte_laser_enviar, name="corte_laser_enviar"),
    path("corte-laser/<int:pk>/regresar-produccion/", views.corte_laser_regresar_produccion, name="corte_laser_regresar_produccion"),
    path("corte-laser/<int:pk>/decote/eliminar/", views.corte_laser_delete_decote, name="corte_laser_delete_decote"),
    path("corte-laser/decote/eliminar-todo/", views.corte_laser_delete_decote_all, name="corte_laser_delete_decote_all"),
    path("corte-laser/catalogos/", views.corte_laser_catalogos, name="corte_laser_catalogos"),
    path("corte-laser/piezas/", views.corte_laser_piezas, name="corte_laser_piezas"),
    path("corte-laser/materiales/", views.corte_laser_materiales, name="corte_laser_materiales"),
    # Alta de una placa sin salir del formulario del pedido. Contesta JSON.
    path("corte-laser/materiales/nuevo/", views.corte_laser_material_nuevo, name="corte_laser_material_nuevo"),
    path("corte-laser/ordenes/", views.corte_laser_ordenes, name="corte_laser_ordenes"),
    path("corte-laser/ordenes/<int:pk>/", views.corte_laser_orden_detalle, name="corte_laser_orden_detalle"),
    path("corte-laser/reportes/", views.corte_laser_reportes, name="corte_laser_reportes"),
    path("corte-laser/reportes/export/", views.corte_laser_reportes_export_html, name="corte_laser_reportes_export_html"),
    path("corte-laser/reportes/export.xlsx", views.corte_laser_reportes_export_xlsx, name="corte_laser_reportes_export_xlsx"),
    path("corte-laser/reportes/terminados/<int:pk>/json/", views.corte_laser_reportes_terminado_json, name="corte_laser_reportes_terminado_json"),
    path("paros/", views.paros, name="paros"),
    path("paros/motivos/", views.paros_motivos, name="paros_motivos"),
    path("paros/fallas/", views.paros_fallas, name="paros_fallas"),
    path("equipos/<int:pk>/editar/", views.equipo_editar, name="equipo_editar"),

    # Bandeja de despacho. Se deduce de la producción, no de una tabla de
    # avisos: un aviso que hay que disparar se puede olvidar de dispararse, y
    # entonces la bandeja sale vacía y parece que no hay nada que despachar.
    path("despacho/", despacho.bandeja, name="despacho"),
    path("despacho/marcar/", despacho.marcar, name="despacho_marcar"),

    # Cuadrillas. Se arman una vez por la mañana y a partir de ahí cada avance
    # del día se anota solo con ellas.
    path("cuadrillas/", cuadrillas.lista, name="cuadrillas"),
    path("cuadrillas/armar/", cuadrillas.armar, name="cuadrilla_armar"),
    path("cuadrillas/<int:pk>/", cuadrillas.armar, name="cuadrilla_editar"),
    path("cuadrillas/<int:pk>/quitar/", cuadrillas.deshacer, name="cuadrilla_deshacer"),

    # Trazabilidad: qué se hizo, con qué equipo y con quién.
    path("trazabilidad/", trazabilidad.tablero, name="trazabilidad"),

    # Producto terminado: qué hay, de quién es y qué falta hacer. Se deduce de
    # los almacenes, los pedidos y las órdenes abiertas de cada línea; no hay
    # un número copiado más que desincronizar. Lo único que se guarda es el
    # mínimo de cada producto, porque eso es una decisión y no un cálculo.
    path("producto-terminado/", terminado.catalogo, name="producto_terminado"),
    path(
        "producto-terminado/minimos/",
        terminado.minimos,
        name="producto_terminado_minimos",
    ),
    path(
        "producto-terminado/minimos/guardar/",
        terminado.guardar_minimo,
        name="producto_terminado_minimo_guardar",
    ),

    # Usuarios. Hasta ahora sólo se podían crear desde el admin de Django.
    path("usuarios/", usuarios.lista, name="usuarios"),
    path("usuarios/nuevo/", usuarios.crear, name="usuario_crear"),
    path("usuarios/<int:pk>/editar/", usuarios.editar, name="usuario_editar"),
    path("usuarios/<int:pk>/contrasena/", usuarios.cambiar_contrasena, name="usuario_contrasena"),
    path("usuarios/<int:pk>/apagar/", usuarios.apagar, name="usuario_apagar"),
]
