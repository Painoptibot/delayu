"""M46 / M62 — аудиоархив и транскрибация."""
from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from delayu.models import AudioArchiveItem


def filter_audio(subsystem, params=None):
    params = params or {}
    qs = AudioArchiveItem.objects.filter(subsystem=subsystem).select_related(
        "case", "created_by"
    )
    q = (params.get("q") or "").strip()
    if q:
        qs = qs.filter(
            Q(title__icontains=q)
            | Q(transcript__icontains=q)
            | Q(case__number__icontains=q)
        )
    st = params.get("source_type", "").strip()
    if st:
        qs = qs.filter(source_type=st)
    case_id = params.get("case")
    if case_id:
        qs = qs.filter(case_id=case_id)
    if params.get("has_transcript") == "1":
        qs = qs.exclude(transcript="")
    return qs.order_by("-recorded_at", "-created_at")


def audio_metrics(subsystem):
    qs = AudioArchiveItem.objects.filter(subsystem=subsystem)
    today = timezone.now().date()
    return {
        "total": qs.count(),
        "with_transcript": qs.exclude(transcript="").count(),
        "calls": qs.filter(source_type=AudioArchiveItem.SourceType.CALL).count(),
        "expiring_soon": qs.filter(
            retention_until__isnull=False,
            retention_until__lte=today + timedelta(days=30),
        ).count(),
    }


def demo_transcribe(item: AudioArchiveItem) -> str:
    text = (
        f"[Демо-транскрипт M62] Запись «{item.title}». "
        f"Длительность {item.duration_sec} сек. "
        "Участники обсудили сроки исполнения и перечень приложений к делу."
    )
    item.transcript = text
    item.save(update_fields=["transcript"])
    return text
