from django import template

register = template.Library()

def _to_float(value):
    try:
        return float(value)
    except Exception:
        return 0.0


@register.filter
def get_item(value, key):
    if isinstance(value, dict):
        return value.get(key, "")
    return ""


@register.filter
def hours_hm(value):
    h = _to_float(value)
    if h <= 0:
        return "0 min"
    total_minutes = int(round(h * 60.0))
    if total_minutes <= 0:
        return "0 min"
    hh = total_minutes // 60
    mm = total_minutes % 60
    if hh <= 0:
        return f"{mm} min"
    if mm <= 0:
        return f"{hh} h"
    return f"{hh} h {mm} min"
