from django import template

from delayu.services.access import user_can
from delayu.services.privacy import mask_value, user_may_view_pii

register = template.Library()


@register.filter(name="can_module")
def can_module(user, module_code: str) -> bool:
    if not module_code:
        return False
    return user_can(user, module_code, "view")


@register.filter(name="mask_pii")
def mask_pii(value, user):
    if value in (None, ""):
        return value
    if user_may_view_pii(user):
        return value
    return mask_value(value, 0)


@register.filter(name="mask_name")
def mask_name(value, user):
    if value in (None, ""):
        return value
    if user_may_view_pii(user):
        return value
    return mask_value(value, 1)
