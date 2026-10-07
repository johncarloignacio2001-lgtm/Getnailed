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


@register.filter
def get_item(dictionary, key):
    if isinstance(dictionary, dict):
        return dictionary.get(key)
    return getattr(dictionary, key, None)


@register.simple_tag(takes_context=True)
def sort_url(context, column):
    request = context.get("request")
    if not request:
        return f"?sort={column}&direction=asc"
    query_dict = request.GET.copy()
    current_sort = query_dict.get("sort")
    current_direction = query_dict.get("direction", "asc")
    if current_sort == column:
        new_direction = "desc" if current_direction == "asc" else "asc"
    else:
        new_direction = "asc"
    query_dict["sort"] = column
    query_dict["direction"] = new_direction
    return f"?{query_dict.urlencode()}"

