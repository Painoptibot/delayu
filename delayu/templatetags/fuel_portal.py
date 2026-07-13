from django import template

from delayu.services.fuel import fuel_apply_azs_url
from delayu.services.fuel_stock import azs_fuel_stock_rows, azs_fuel_stock_summary

register = template.Library()


@register.simple_tag(takes_context=True)
def fuel_apply_azs_url_tag(context, azs_pk):
    request = context.get("request")
    if not request:
        return ""
    return fuel_apply_azs_url(request, int(azs_pk))


@register.filter
def fuel_stock_rows(azs):
    return azs_fuel_stock_rows(azs)


@register.filter
def fuel_stock_summary(azs):
    return azs_fuel_stock_summary(azs)


@register.filter
def redeem_display_liters(redeem):
    """Фактический объём: подтверждение жителя, иначе запись АЗС."""
    reported = getattr(redeem, "citizen_reported_liters", None)
    if reported is not None:
        return reported
    return getattr(redeem, "liters", 0)
