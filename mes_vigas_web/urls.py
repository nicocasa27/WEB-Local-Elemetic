"""
URL configuration for mes_vigas_web project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import include, path, re_path

from mes_vigas_web.media_views import servir_media

urlpatterns = [
    path('accounts/', include('django.contrib.auth.urls')),
    # El teclado de la tableta del piso: cuatro dígitos y a trabajar.
    path('pin/', include('acceso.urls')),
    path('', include('produccion.urls')),
    path('catalogos/', include('catalogos.urls')),
    path('configuracion/', include('nucleo.urls')),
    path('almacen/', include('inventario.urls')),
    path('personal/', include('personal.urls')),
    path('admin/', admin.site.urls),

    # Los archivos subidos (planos, DXF, comprobantes de envío) se sirven
    # siempre por esta vista, no sólo con DEBUG activo, y siempre exigiendo
    # sesión iniciada. Ver mes_vigas_web/media_views.py.
    re_path(r'^media/(?P<ruta>.*)$', servir_media, name='media'),
]
