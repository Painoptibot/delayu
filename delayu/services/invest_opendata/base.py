"""Shared types for open-data source adapters."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

EntityKind = Literal["investor", "project", "site"]
Severity = Literal["info", "warn", "hard"]
ResultStatus = Literal["ok", "empty", "error", "skipped"]


@dataclass
class CheckContext:
    subsystem: Any
    entity_kind: EntityKind
    inn: str = ""
    cadastral: str = ""
    latitude: float | None = None
    longitude: float | None = None
    investor: Any = None
    project: Any = None
    site: Any = None
    live: bool = False
    mock: bool = True
    extras: dict[str, Any] = field(default_factory=dict)


@dataclass
class SourceResult:
    source_code: str
    status: ResultStatus = "ok"
    severity: Severity = "info"
    title: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    external_url: str = ""
    error_text: str = ""


class SourceAdapter(Protocol):
    code: str
    entity_kinds: tuple[EntityKind, ...]
    label: str

    def check(self, ctx: CheckContext) -> SourceResult: ...
