from django.conf import settings

def my_setting(request):
    return {'MY_SETTING': settings}

def language_code(request):
    return {"LANGUAGE_CODE": request.LANGUAGE_CODE}

def get_cookie(request):
    return {"COOKIES": request.COOKIES}

# Add the 'ENVIRONMENT' setting to the template context
def environment(request):
    return {'ENVIRONMENT': settings.ENVIRONMENT}


def yandex_maps(request):
    return {"yandex_maps_api_key": getattr(settings, "YANDEX_MAPS_API_KEY", "")}


def dadata_integration(request):
    enabled = bool(getattr(settings, "DADATA_API_KEY", "").strip())
    if enabled and not getattr(request.user, "is_authenticated", False):
        enabled = False
    return {"dadata_enabled": enabled}


def delayu_nav(request):
    if not request.user.is_authenticated:
        return {}
    from delayu.menu import get_active_membership

    membership = get_active_membership(request.user)
    memberships = []
    if hasattr(request.user, "subsystem_memberships"):
        memberships = list(
            request.user.subsystem_memberships.select_related(
                "subsystem", "organization", "role"
            )
        )
    unread = 0
    if membership:
        from delayu.models import Notification

        unread = Notification.objects.filter(
            user=request.user, subsystem=membership.subsystem, is_read=False
        ).count()
    return {
        "active_membership": membership,
        "user_memberships": memberships,
        "unread_notifications": unread,
    }


def delayu_tz(request):
    """ТЗ в контексте для страниц входа (без auth)."""
    from delayu.tz_docs import tz_context

    return tz_context()
