"""Capa de servicios: la lógica de negocio, fuera de las vistas.

Un servicio no recibe `request` ni devuelve respuestas HTTP. Recibe datos y el
usuario que actúa, abre su propia transacción sobre la base `mes`, y lanza las
excepciones de `core.excepciones` cuando una regla no se cumple. Traducir eso a
un mensaje en pantalla es cosa de la vista.

De ahí salen tres cosas que hoy no se pueden hacer: probar una regla sin montar
una petición, reutilizarla desde un comando o una tarea programada, y cambiarla
en un solo sitio en vez de en los cuatro módulos que la tienen copiada.
"""
