"""Контекст подсистемы — обёртки над delayu.menu."""
from __future__ import annotations

from delayu.menu import ensure_superuser_membership, get_active_membership

__all__ = ["get_active_membership", "ensure_superuser_membership", "get_effective_membership"]


def get_effective_membership(user, subsystem_id=None):
    return get_active_membership(user, subsystem_id=subsystem_id)
