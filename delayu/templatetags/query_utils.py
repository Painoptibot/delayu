from django import template

register = template.Library()


@register.simple_tag
def url_replace(request, **kwargs):
    """Сохранить GET-параметры при смене page и др."""
    params = request.GET.copy()
    for key, value in kwargs.items():
        if value is None:
            params.pop(key, None)
        else:
            params[key] = str(value)
    encoded = params.urlencode()
    return encoded
