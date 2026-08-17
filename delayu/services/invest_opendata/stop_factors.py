"""Stop-factor sync from open-data hard findings."""
from __future__ import annotations

from django.utils import timezone

from delayu.models_invest import InvestProject, InvestStopFactor

STOP_PREFIX = "Открытые данные:"


def _title(source_code: str, short: str) -> str:
    short = (short or source_code).strip()[:180]
    return f"{STOP_PREFIX} {source_code} — {short}"


def projects_for_context(*, investor=None, project=None, site=None) -> list[InvestProject]:
    if project is not None:
        return [project]
    projects: list[InvestProject] = []
    if investor is not None:
        projects.extend(list(investor.projects.all()))
    if site is not None:
        for link in site.project_links.select_related("project"):
            if link.project_id and link.project not in projects:
                projects.append(link.project)
    # unique by pk
    seen = set()
    out = []
    for p in projects:
        if p.pk in seen:
            continue
        seen.add(p.pk)
        out.append(p)
    return out


def sync_opendata_stop_factors(
    *,
    projects: list[InvestProject],
    hard_items: list[tuple[str, str]],
) -> None:
    """
    hard_items: list of (source_code, short_title).
    Ensures blocking SF for each; resolves previously open opendata SF whose source is gone.
    """
    wanted_titles = {_title(code, short) for code, short in hard_items}
    for project in projects:
        existing = list(
            InvestStopFactor.objects.filter(
                project=project,
                title__startswith=STOP_PREFIX,
            )
        )
        existing_by_title = {sf.title: sf for sf in existing}
        for code, short in hard_items:
            title = _title(code, short)
            sf = existing_by_title.get(title)
            if sf is None:
                InvestStopFactor.objects.get_or_create(
                    project=project,
                    title=title,
                    defaults={"status": InvestStopFactor.Status.BLOCKING},
                )
            elif sf.status in (
                InvestStopFactor.Status.OPEN,
                InvestStopFactor.Status.RESOLVED,
            ):
                sf.status = InvestStopFactor.Status.BLOCKING
                sf.resolved_at = None
                sf.save(update_fields=["status", "resolved_at"])
        for sf in existing:
            if sf.title in wanted_titles:
                continue
            if sf.status in (InvestStopFactor.Status.OPEN, InvestStopFactor.Status.BLOCKING):
                sf.status = InvestStopFactor.Status.RESOLVED
                sf.resolved_at = timezone.now()
                sf.save(update_fields=["status", "resolved_at"])
