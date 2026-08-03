"""Infraestructura compartida entre las aplicaciones del MES.

`core` no tiene modelos ni vistas: reúne lo que hoy está repetido o disperso
por catalogos/views.py y produccion/views.py, para que exista un solo sitio
donde cambiarlo. Es el paso previo a extraer la capa de servicios.
"""
