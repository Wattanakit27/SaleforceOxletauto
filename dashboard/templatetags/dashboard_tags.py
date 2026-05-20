from django import template
from django.utils.safestring import mark_safe

from dashboard.services.helpers import dots_html, urg_badge_html, pct, nc

register = template.Library()


@register.filter
def dots(update_count):
    return mark_safe(dots_html(int(update_count)))


@register.filter
def urg_badge(update_count):
    return mark_safe(urg_badge_html(int(update_count)))


@register.filter
def percentage(a, b):
    try:
        return pct(int(a), int(b))
    except (ValueError, TypeError):
        return 0


@register.filter
def need_calls(update_count):
    return nc(int(update_count))


@register.filter
def format_number(value):
    try:
        return f"{int(value):,}"
    except (ValueError, TypeError):
        return value


@register.filter
def format_price(value):
    try:
        return f"฿{int(float(value)):,}"
    except (ValueError, TypeError):
        return value


@register.filter
def get_item(dictionary, key):
    """Get item from dict in template."""
    if isinstance(dictionary, dict):
        return dictionary.get(key)
    return None


@register.filter
def multiply(value, arg):
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return 0
