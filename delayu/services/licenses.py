"""Выдача лицензий заказчикам и мест пользователям (M83)."""
import secrets
from datetime import date

from django.db import transaction

from delayu.models import CustomerLicense, LicenseSeat, Organization, SubsystemMembership


class LicenseError(Exception):
    pass


def new_license_number() -> str:
    for _ in range(8):
        number = "DL-" + secrets.token_hex(4).upper()
        if not CustomerLicense.objects.filter(number=number).exists():
            return number
    raise LicenseError("Не удалось выдать номер лицензии.")


def license_visual(lic: CustomerLicense, used: int) -> dict:
    """Данные для карточки лицензии: тон, штамп и отметки мест."""
    seats = lic.seats or 0
    if license_is_usable(lic):
        tone, stamp = "ok", "Действует"
    elif lic.status == CustomerLicense.Status.SUSPENDED:
        tone, stamp = "warn", "Приостановлена"
    elif lic.status == CustomerLicense.Status.REVOKED:
        tone, stamp = "bad", "Отозвана"
    elif lic.status == CustomerLicense.Status.DRAFT:
        tone, stamp = "mute", "Черновик"
    else:
        tone, stamp = "warn", "Не действует"
    filled = min(used, seats)
    return {
        "tone": tone,
        "stamp": stamp,
        "percent": min(100, round(used * 100 / seats)) if seats else 0,
        "marks": [{"filled": index < filled} for index in range(seats)],
    }


CONTOUR_LICENSE_ALIAS = {
    "U01": "M22",
    "U02": "M24",
    "U03": "M15",
    "U04": "M12",
    "I01": "M22",
    "I02": "M15",
    "F01": "M22",
    "F02": "M15",
}


def license_covers(lic: CustomerLicense, module_code: str) -> bool:
    codes = set(lic.modules.values_list("code", flat=True))
    if not codes:
        return True
    if module_code in codes:
        return True
    legacy = CONTOUR_LICENSE_ALIAS.get(module_code)
    return bool(legacy and legacy in codes)


def license_allows(membership, module_code: str) -> bool:
    """Место на действующей лицензии. Пока мест нет, контур ещё не переведён на допуск."""
    if module_code == "M83":
        return True
    if not CustomerLicense.objects.filter(subsystem_id=membership.subsystem_id).exists():
        return True
    if not LicenseSeat.objects.filter(license__subsystem_id=membership.subsystem_id).exists():
        return True
    seats = LicenseSeat.objects.filter(
        user_id=membership.user_id,
        license__subsystem_id=membership.subsystem_id,
        license__organization_id=membership.organization_id,
    ).select_related("license")
    for seat in seats:
        if license_is_usable(seat.license) and license_covers(seat.license, module_code):
            return True
    return False


def license_is_usable(lic: CustomerLicense, today=None) -> bool:
    today = today or date.today()
    if lic.status != CustomerLicense.Status.ACTIVE:
        return False
    if lic.valid_from and lic.valid_from > today:
        return False
    if lic.valid_until and lic.valid_until < today:
        return False
    return True


def seats_used(lic: CustomerLicense) -> int:
    return lic.seat_assignments.count()


def support_ended_notice(membership, today=None):
    """Плашка, если у лицензии организации дата «Поддержка до» уже прошла.

    Сама дата поддержки ещё входит в срок. Пустая дата означает, что срок не задан.
    """
    if not membership or not membership.subsystem_id:
        return None
    today = today or date.today()
    qs = CustomerLicense.objects.filter(
        subsystem_id=membership.subsystem_id,
        support_until__isnull=False,
        support_until__lt=today,
    ).exclude(status=CustomerLicense.Status.REVOKED)
    if membership.organization_id:
        qs = qs.filter(organization_id=membership.organization_id)
    lic = qs.order_by("support_until").first()
    if not lic:
        return None
    return {"until": lic.support_until, "number": lic.number}


@transaction.atomic
def issue_license(*, subsystem, organization, title, seats, valid_from, valid_until, support_until, note, modules, issued_by):
    if organization.subsystem_id != subsystem.id:
        raise LicenseError("Заказчик не относится к этому контуру.")
    if seats < 1:
        raise LicenseError("В лицензии должно быть хотя бы одно место.")
    lic = CustomerLicense.objects.create(
        subsystem=subsystem,
        organization=organization,
        number=new_license_number(),
        title=title.strip() or organization.name,
        status=CustomerLicense.Status.ACTIVE,
        seats=seats,
        valid_from=valid_from,
        valid_until=valid_until,
        support_until=support_until,
        note=note or "",
        issued_by=issued_by,
    )
    if modules:
        lic.modules.set(modules)
    return lic


@transaction.atomic
def assign_seat(lic: CustomerLicense, user, assigned_by):
    if not license_is_usable(lic):
        raise LicenseError("Лицензия не действует: место выдать нельзя.")
    if seats_used(lic) >= lic.seats:
        raise LicenseError("Свободных мест нет.")
    member = SubsystemMembership.objects.filter(
        user=user, subsystem=lic.subsystem, organization=lic.organization
    ).exists()
    if not member:
        raise LicenseError("Пользователь не состоит в организации заказчика.")
    seat, created = LicenseSeat.objects.get_or_create(
        license=lic,
        user=user,
        defaults={"assigned_by": assigned_by},
    )
    if not created:
        raise LicenseError("Этому пользователю место уже выдано.")
    from delayu.services.audit import log_action

    log_action(
        assigned_by,
        lic.subsystem,
        "license.seat_assign",
        "LicenseSeat",
        seat.pk,
        {"license": lic.number, "user": user.username},
    )
    return seat


@transaction.atomic
def release_seat(lic: CustomerLicense, seat_id):
    seat = lic.seat_assignments.filter(pk=seat_id).first()
    if not seat:
        raise LicenseError("Место не найдено.")
    seat.delete()


def customer_choices(subsystem):
    return Organization.objects.filter(subsystem=subsystem, is_active=True).order_by("name")


def assignable_users(lic: CustomerLicense):
    taken = lic.seat_assignments.values_list("user_id", flat=True)
    memberships = (
        SubsystemMembership.objects.filter(
            subsystem=lic.subsystem, organization=lic.organization
        )
        .exclude(user_id__in=taken)
        .select_related("user", "role")
        .order_by("user__username")
    )
    seen = set()
    users = []
    for membership in memberships:
        if membership.user_id in seen:
            continue
        seen.add(membership.user_id)
        users.append(membership.user)
    return users
