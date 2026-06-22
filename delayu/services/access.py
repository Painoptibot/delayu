"""Права доступа: модуль × подсистема × роль."""
from functools import wraps

from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404

from delayu.menu import get_active_membership
from delayu.models import ModuleCatalog, SubsystemModule


def user_can(user, module_code: str, action: str = "view") -> bool:
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    membership = get_active_membership(user)
    if not membership:
        return False
    if not SubsystemModule.objects.filter(
        subsystem=membership.subsystem,
        module__code=module_code,
        enabled=True,
    ).exists():
        return False
    try:
        module = ModuleCatalog.objects.get(code=module_code)
    except ModuleCatalog.DoesNotExist:
        return False
    from delayu.services.role_inheritance import role_has_action

    return role_has_action(membership.role, module, action)


def require_module(module_code: str, action: str = "view"):
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            if not user_can(request.user, module_code, action):
                raise PermissionDenied(f"Нет доступа к модулю {module_code}")
            return view_func(request, *args, **kwargs)

        return _wrapped

    return decorator


def get_membership_or_403(request):
    from delayu.menu import get_active_membership

    membership = get_active_membership(request.user)
    if not membership:
        raise PermissionDenied("Нет активной подсистемы")
    return membership
