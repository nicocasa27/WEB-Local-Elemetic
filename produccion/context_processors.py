def user_access(request):
    user = getattr(request, "user", None)
    is_auth = bool(user and getattr(user, "is_authenticated", False))
    is_admin = False
    can_pedidos = False
    can_logistica_corta = False
    role = ""
    can_corte = False
    can_soldadura = False
    can_robotica = False
    can_herreria = False
    can_corte_laser = False
    try:
        if is_auth:
            can_corte = bool(user.groups.filter(name="corte").exists())
            can_soldadura = bool(user.groups.filter(name="soldadura").exists())
            can_robotica = bool(user.groups.filter(name="robotica").exists())
            can_herreria = bool(
                user.groups.filter(name__in=["herreria", "herreria_supervision"]).exists()
            )
            can_corte_laser = bool(
                user.groups.filter(name__in=["corte_laser", "corte_laser_supervision"]).exists()
            )
            is_admin = bool(
                getattr(user, "is_superuser", False)
                or getattr(user, "is_staff", False)
                or user.groups.filter(name__in=["admin_general", "ingenieria_civil"]).exists()
            )
            can_pedidos = bool(
                getattr(user, "is_superuser", False)
                or user.groups.filter(name__in=["admin_general", "ingenieria_civil", "pedidos_ventas"]).exists()
            )
            can_logistica_corta = bool(can_corte_laser or can_pedidos or is_admin)
            if is_admin:
                role = "admin"
            elif can_corte:
                role = "corte"
            elif can_soldadura:
                role = "soldadura"
            elif can_robotica:
                role = "robotica"
            elif can_herreria:
                role = "herreria"
            elif can_corte_laser:
                role = "corte_laser"
    except Exception:
        is_admin = False
        can_pedidos = False
        can_logistica_corta = False
        role = ""
        can_corte = False
        can_soldadura = False
        can_robotica = False
        can_herreria = False
        can_corte_laser = False
    return {
        "is_admin": is_admin,
        "can_pedidos": can_pedidos,
        "can_logistica_corta": can_logistica_corta,
        "user_role": role,
        "can_corte": can_corte or is_admin,
        "can_soldadura": can_soldadura or is_admin,
        "can_robotica": can_robotica or is_admin,
        "can_herreria": can_herreria or is_admin,
        "can_corte_laser": can_corte_laser or is_admin,
    }
