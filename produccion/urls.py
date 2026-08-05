from django.urls import path

from . import movil, panorama, views

app_name = "produccion"

urlpatterns = [
    path("", views.home, name="home"),
    # La pantalla del operador: sólo su trabajo, y un toque por pieza.
    path("movil/", movil.mi_trabajo, name="movil"),
    # Las cuatro líneas en una sola lista. La pregunta «¿qué se está
    # produciendo?» no tenía pantalla: había que abrir cuatro y sumar.
    path("control/", panorama.control, name="control"),
    path("menu/", views.home, name="menu"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("dashboard/export/", views.dashboard_export_html, name="dashboard_export_html"),
    path("dashboard/export.xlsx", views.dashboard_export_xlsx, name="dashboard_export_xlsx"),
    path("dashboard/quien/<int:colab_id>/<str:etapa>/", views.dashboard_quien_detalle, name="dashboard_quien_detalle"),
    path("vigas/global/", views.viga_global, name="viga_global"),
    path("solo-lectura/produccion/", views.solo_lectura_produccion, name="solo_lectura_produccion"),
    path("solo-lectura/robotica/", views.solo_lectura_robotica, name="solo_lectura_robotica"),
    path("solo-lectura/herreria/", views.solo_lectura_herreria, name="solo_lectura_herreria"),
    path("solo-lectura/corte-laser/", views.solo_lectura_corte_laser, name="solo_lectura_corte_laser"),
    path("area/corte/", views.area_corte, name="area_corte"),
    path("area/soldadura/", views.area_soldadura, name="area_soldadura"),
    path("vigas/", views.viga_list, name="viga_list"),
    path("vigas/nueva/", views.viga_create, name="viga_create"),
    path("vigas/<int:pk>/enviar/", views.viga_enviar, name="viga_enviar"),
    path("vigas/<int:pk>/regresar/", views.viga_regresar_produccion, name="viga_regresar_produccion"),
    path("vigas/<int:pk>/editar/", views.viga_update, name="viga_update"),
    path("vigas/<int:pk>/eliminar/", views.viga_delete, name="viga_delete"),
    path("vigas/<int:pk>/eliminar-decote/", views.viga_delete_decote, name="viga_delete_decote"),
    path("vigas/eliminar-decote/", views.viga_delete_decote_all, name="viga_delete_decote_all"),
    path("vigas/<int:pk>/estado/", views.viga_change_status, name="viga_change_status"),
    path("vigas/<int:pk>/estado-json/", views.viga_change_status_json, name="viga_change_status_json"),
    path("vigas/<int:pk>/asignaciones/", views.viga_asignaciones, name="viga_asignaciones"),
    path("vigas/<int:pk>/meta-json/", views.viga_update_meta_json, name="viga_update_meta_json"),
    path("export/vigas.xlsx", views.export_vigas_excel, name="export_vigas_excel"),
]
