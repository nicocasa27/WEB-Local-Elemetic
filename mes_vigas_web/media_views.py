"""Entrega de archivos subidos, detrás de sesión iniciada.

Dos problemas que resuelve la misma vista:

1. `urls.py` sólo servía MEDIA_URL cuando DEBUG estaba activo. Al pasar a
   producción con DEBUG apagado, los planos en PDF, los DXF y los
   comprobantes de envío dejaban de descargarse: funcionalidad rota, no un
   detalle de configuración.

2. Mientras se servían, se servían a cualquiera. Un acuse de entrega firmado
   o el plano de un cliente estaban disponibles para quien acertara la URL,
   sin iniciar sesión.

Servir archivos desde Django no es lo más rápido, pero el taller ejecuta la
aplicación con `runserver` y estos archivos se abren de uno en uno. Cuando se
monte un proxy delante, esta vista se sustituye por un `X-Accel-Redirect` de
nginx conservando la misma comprobación de sesión.
"""

import mimetypes
from pathlib import Path

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404
from django.views.decorators.http import require_http_methods


@login_required
@require_http_methods(["GET", "HEAD"])
def servir_media(request, ruta):
    raiz = Path(settings.MEDIA_ROOT).resolve()

    try:
        destino = (raiz / ruta).resolve()
    except (OSError, ValueError):
        raise Http404("Archivo no encontrado")

    # Impide salirse de MEDIA_ROOT con ../ o con un enlace simbólico.
    if not destino.is_relative_to(raiz):
        raise Http404("Archivo no encontrado")

    if not destino.is_file():
        raise Http404("Archivo no encontrado")

    tipo, _ = mimetypes.guess_type(str(destino))
    return FileResponse(destino.open("rb"), content_type=tipo or "application/octet-stream")
