"""M67–M72 — геопортал, PWA, SSO, ETL, витрина, портал гражданина."""
import random
from decimal import Decimal

from django.db.models import Q
from django.utils import timezone

from delayu.models import (
    CitizenAppeal,
    DataDataset,
    EtlJob,
    EtlRun,
    GeoLayer,
    GeoObject,
    PwaDevice,
    PwaDraft,
    SsoProvider,
)


def infra_hub_metrics(subsystem):
    return {
        "geo_objects": GeoObject.objects.filter(subsystem=subsystem).count(),
        "pwa_devices": PwaDevice.objects.filter(subsystem=subsystem).count(),
        "pwa_drafts_pending": PwaDraft.objects.filter(
            device__subsystem=subsystem, synced_at__isnull=True
        ).count(),
        "sso_active": SsoProvider.objects.filter(subsystem=subsystem, is_active=True).count(),
        "etl_failed": EtlRun.objects.filter(
            job__subsystem=subsystem, status=EtlRun.Status.FAILED
        ).count(),
        "datasets_published": DataDataset.objects.filter(
            subsystem=subsystem, is_published=True
        ).count(),
        "appeals_new": CitizenAppeal.objects.filter(
            subsystem=subsystem, status=CitizenAppeal.Status.NEW
        ).count(),
    }


def filter_geo_layers(subsystem, params=None):
    params = params or {}
    qs = GeoLayer.objects.filter(subsystem=subsystem)
    if params.get("visible") == "1":
        qs = qs.filter(is_visible=True)
    q = (params.get("q") or "").strip()
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(code__icontains=q))
    return qs


def filter_geo_objects(subsystem, params=None):
    params = params or {}
    qs = GeoObject.objects.filter(subsystem=subsystem).select_related("layer", "case")
    layer_id = params.get("layer")
    if layer_id:
        qs = qs.filter(layer_id=layer_id)
    case_id = params.get("case")
    if case_id:
        qs = qs.filter(case_id=case_id)
    q = (params.get("q") or "").strip()
    if q:
        qs = qs.filter(Q(title__icontains=q) | Q(address__icontains=q))
    return qs


def geo_objects_for_map(subsystem):
    return [
        {
            "id": o.id,
            "title": o.title,
            "address": o.address,
            "lat": float(o.latitude),
            "lng": float(o.longitude),
            "layer": o.layer.name,
            "color": o.layer.color,
            "case_id": o.case_id,
        }
        for o in filter_geo_objects(subsystem).filter(layer__is_visible=True)[:200]
    ]


def demo_geocode(address: str):
    """Демо-геокодирование: псевдокоординаты по хэшу строки."""
    base = sum(ord(c) for c in (address or "moscow")) % 1000
    lat = Decimal("55.7") + Decimal(base) / Decimal("10000")
    lng = Decimal("37.6") + Decimal(base % 500) / Decimal("10000")
    return lat, lng


def filter_pwa_devices(subsystem, params=None):
    params = params or {}
    qs = PwaDevice.objects.filter(subsystem=subsystem).select_related("user")
    user_id = params.get("user")
    if user_id:
        qs = qs.filter(user_id=user_id)
    return qs.order_by("-last_sync_at")


def filter_pwa_drafts(subsystem, *, pending_only=False):
    qs = PwaDraft.objects.filter(device__subsystem=subsystem).select_related("device", "device__user")
    if pending_only:
        qs = qs.filter(synced_at__isnull=True)
    return qs.order_by("-created_at")


def sync_pwa_draft(draft: PwaDraft):
    draft.synced_at = timezone.now()
    draft.save(update_fields=["synced_at"])
    device = draft.device
    device.last_sync_at = timezone.now()
    device.save(update_fields=["last_sync_at"])
    return draft


def filter_sso_providers(subsystem, params=None):
    params = params or {}
    qs = SsoProvider.objects.filter(subsystem=subsystem)
    if params.get("active") == "1":
        qs = qs.filter(is_active=True)
    return qs.order_by("name")


def filter_etl_jobs(subsystem, params=None):
    params = params or {}
    qs = EtlJob.objects.filter(subsystem=subsystem)
    if params.get("active") == "1":
        qs = qs.filter(is_active=True)
    return qs.order_by("name")


def filter_etl_runs(subsystem, params=None):
    params = params or {}
    qs = EtlRun.objects.filter(job__subsystem=subsystem).select_related("job")
    status = (params.get("status") or "").strip()
    if status:
        qs = qs.filter(status=status)
    job_id = params.get("job")
    if job_id:
        qs = qs.filter(job_id=job_id)
    return qs.order_by("-started_at")


def run_etl_job(job: EtlJob):
    """Демо-запуск ETL: случайный успех/ошибка с подсчётом строк."""
    run = EtlRun.objects.create(job=job, status=EtlRun.Status.RUNNING)
    ok = random.randint(50, 500)
    err = random.randint(0, 5) if random.random() > 0.85 else 0
    error_rows = []
    if err:
        for row in range(1, err + 1):
            error_rows.append(
                {
                    "row": row * 17,
                    "field": "inn" if row % 2 else "date",
                    "value": f"bad-{row}",
                    "message": "Некорректный формат поля",
                }
            )
    run.rows_ok = ok
    run.rows_err = err
    run.error_rows = error_rows
    run.finished_at = timezone.now()
    if err > 3:
        run.status = EtlRun.Status.FAILED
        run.log = f"Ошибка разбора {job.source_type}: {err} строк с ошибками."
    else:
        run.status = EtlRun.Status.SUCCESS
        run.log = f"Загружено {ok} записей, отклонено {err}."
    run.save()
    return run


def filter_datasets(subsystem, params=None):
    params = params or {}
    qs = DataDataset.objects.filter(subsystem=subsystem)
    if params.get("published") == "1":
        qs = qs.filter(is_published=True)
    q = (params.get("q") or "").strip()
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(slug__icontains=q))
    return qs.order_by("name")


def filter_citizen_appeals(subsystem, params=None):
    params = params or {}
    qs = CitizenAppeal.objects.filter(subsystem=subsystem).select_related("case")
    status = (params.get("status") or "").strip()
    if status:
        qs = qs.filter(status=status)
    q = (params.get("q") or "").strip()
    if q:
        qs = qs.filter(
            Q(public_id__icontains=q)
            | Q(applicant_name__icontains=q)
            | Q(subject__icontains=q)
        )
    return qs.order_by("-created_at")
