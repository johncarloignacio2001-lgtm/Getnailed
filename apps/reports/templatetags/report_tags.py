from datetime import date, datetime
from decimal import Decimal

from django import template


register = template.Library()


@register.filter
def report_value(value):
    if isinstance(value, Decimal):
        return f"{value:,.2f}"
    if isinstance(value, (date, datetime)):
        return value.strftime("%Y-%m-%d")
    return value
