from django import template

from delayu.services.fuel import fuel_apply_azs_url

register = template.Library()


@register.simple_tag(takes_context=True)
def fuel_apply_azs_url_tag(context, azs_pk):
    request = context.get("request")
    if not request:
        return ""
    return fuel_apply_azs_url(request, int(azs_pk))
