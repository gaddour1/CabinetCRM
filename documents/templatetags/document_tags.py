from django import template
from django.utils.html import format_html

register = template.Library()


@register.filter
def document_value(value):
    if value is None or value == "" or (isinstance(value, str) and not value.strip()):
        return format_html('<span class="missing">Non renseigné</span>')
    return value
