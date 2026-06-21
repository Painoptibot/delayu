"""Создание и обновление пользователей M03."""
from django.contrib.auth import get_user_model
from django.db import transaction

from delayu.models import SubsystemMembership
from delayu.models_business import UserProfile

User = get_user_model()


def get_or_create_profile(user) -> UserProfile:
    profile, _ = UserProfile.objects.get_or_create(user=user)
    return profile


def user_card_context(user, membership):
    """Контекст для модальной карточки: значения всех атрибутов по группам."""
    profile = get_or_create_profile(user)
    groups = []
    for group in UserProfile.attribute_groups():
        rows = []
        for key, label in group["fields"]:
            if key in ("username", "email", "is_active", "last_login"):
                if key == "username":
                    val = user.username
                elif key == "email":
                    val = user.email
                elif key == "is_active":
                    val = "Да" if user.is_active else "Нет"
                elif key == "last_login":
                    val = user.last_login.strftime("%d.%m.%Y %H:%M") if user.last_login else "—"
            else:
                raw = getattr(profile, key, None)
                if key == "gender":
                    val = profile.get_gender_display()
                elif key == "employment_type":
                    val = profile.get_employment_type_display()
                elif isinstance(raw, bool):
                    val = "Да" if raw else "Нет"
                elif hasattr(raw, "strftime"):
                    val = raw.strftime("%d.%m.%Y") if raw else "—"
                else:
                    val = raw or "—"
            rows.append({"key": key, "label": label, "value": val})
        groups.append({"title": group["title"], "rows": rows})
    return {
        "user": user,
        "profile": profile,
        "membership": membership,
        "attribute_groups_display": groups,
    }


@transaction.atomic
def create_user_with_membership(
    *,
    subsystem,
    username,
    email,
    password,
    first_name,
    last_name,
    organization,
    role,
    profile_data,
):
    user = User.objects.create_user(
        username=username,
        email=email,
        password=password,
        first_name=first_name,
        last_name=last_name,
    )
    profile = get_or_create_profile(user)
    for key, value in profile_data.items():
        if value is not None and value != "":
            setattr(profile, key, value)
    profile.active_subsystem = subsystem
    profile.save()
    SubsystemMembership.objects.create(
        user=user,
        subsystem=subsystem,
        organization=organization,
        role=role,
        is_default=True,
    )
    return user


@transaction.atomic
def update_user_membership(
    *,
    user,
    membership,
    user_fields,
    password,
    organization,
    role,
    profile_data,
):
    for attr, value in user_fields.items():
        setattr(user, attr, value)
    if password:
        user.set_password(password)
    user.save()
    profile = get_or_create_profile(user)
    for key, value in profile_data.items():
        setattr(profile, key, value)
    profile.save()
    membership.organization = organization
    membership.role = role
    membership.save()
    return user


def deactivate_user(user):
    user.is_active = False
    user.save(update_fields=["is_active"])
