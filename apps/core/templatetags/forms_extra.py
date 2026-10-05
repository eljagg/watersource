"""Template helpers for the sectioned form layout (templates/partials/form_*.html).

Registered as a template builtin in settings, so no ``{% load %}`` is needed.
"""
from django import template

register = template.Library()


@register.filter
def add_fields(first, second):
    """Chain bound fields into a list: ``f.a|add_fields:f.b|add_fields:f.c``.

    Lets a template hand a hand-picked group of fields to
    ``partials/form_section.html`` without a view-side helper.
    """
    out = list(first) if isinstance(first, list) else [first]
    if second is not None:
        out.append(second)
    return out


@register.filter
def get_item(mapping, key):
    """Dictionary lookup by variable key: ``{{ titles|get_item:slug }}``."""
    try:
        return mapping.get(key, "")
    except AttributeError:
        return ""


@register.simple_tag(takes_context=True)
def active_tab(context, *prefixes):
    """Return ``is-active`` when the current path starts with any of ``prefixes`` (navigation tabs)."""
    request = context.get("request")
    path = getattr(request, "path", "") or ""
    return "is-active" if any(path.startswith(p) for p in prefixes) else ""


@register.filter
def has_role(user, name):
    """``{% if user|has_role:"finance" %}`` — role (group) membership check for templates."""
    return bool(getattr(user, "is_authenticated", False)) and user.has_role(name)
