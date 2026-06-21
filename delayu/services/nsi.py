"""M73 — центральные справочники НСИ."""
from django.db.models import Count, Q

from delayu.models import NSIClassifier, NSIValue


def filter_classifiers(subsystem, params=None):
    params = params or {}
    qs = NSIClassifier.objects.filter(subsystem=subsystem).annotate(
        value_count=Count("values")
    )
    if params.get("active") == "1":
        qs = qs.filter(is_active=True)
    q = (params.get("q") or "").strip()
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(code__icontains=q))
    return qs.order_by("name")


def filter_values(classifier, params=None):
    params = params or {}
    qs = NSIValue.objects.filter(classifier=classifier).select_related("parent")
    if params.get("active") == "1":
        qs = qs.filter(is_active=True)
    q = (params.get("q") or "").strip()
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(code__icontains=q))
    return qs.order_by("sort_order", "name")


def nsi_metrics(subsystem):
    classifiers = NSIClassifier.objects.filter(subsystem=subsystem)
    return {
        "classifiers": classifiers.count(),
        "classifiers_active": classifiers.filter(is_active=True).count(),
        "values": NSIValue.objects.filter(classifier__subsystem=subsystem).count(),
    }
