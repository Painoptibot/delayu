"""Managed Odysseus vendor updates (pin / check / apply / rollback)."""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings

from delayu.models_odysseus import OdysseusSettings
from delayu.services.odysseus_settings import ensure_odysseus_settings


@dataclass
class UpdateCheckResult:
    pinned_ref: str
    head_ref: str
    upstream_url: str
    vendor_exists: bool
    message: str


def _repo_root() -> Path:
    return Path(settings.BASE_DIR)


def vendor_dir(cfg: OdysseusSettings) -> Path:
    return _repo_root() / (cfg.vendor_path or "vendor/odysseus")


def _run_git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )


def check_update(subsystem) -> UpdateCheckResult:
    cfg = ensure_odysseus_settings(subsystem)
    path = vendor_dir(cfg)
    if not path.exists() or not (path / ".git").exists():
        return UpdateCheckResult(
            pinned_ref=cfg.pinned_ref,
            head_ref="",
            upstream_url=cfg.upstream_url,
            vendor_exists=False,
            message="vendor missing — clone per docs/odysseus-local.md",
        )
    head = _run_git(path, "rev-parse", "HEAD")
    head_ref = (head.stdout or "").strip() if head.returncode == 0 else ""
    fetch = _run_git(path, "fetch", "--tags", "--quiet")
    msg = "ok"
    if fetch.returncode != 0:
        msg = f"fetch warning: {(fetch.stderr or '')[:200]}"
    return UpdateCheckResult(
        pinned_ref=cfg.pinned_ref or head_ref,
        head_ref=head_ref,
        upstream_url=cfg.upstream_url,
        vendor_exists=True,
        message=msg,
    )


def apply_update(subsystem, ref: str) -> UpdateCheckResult:
    cfg = ensure_odysseus_settings(subsystem)
    path = vendor_dir(cfg)
    if not path.exists():
        raise FileNotFoundError(f"vendor not found: {path}")
    current = _run_git(path, "rev-parse", "HEAD")
    current_ref = (current.stdout or "").strip()
    fetch = _run_git(path, "fetch", "--tags", "--quiet")
    if fetch.returncode != 0:
        raise RuntimeError(fetch.stderr or "git fetch failed")
    checkout = _run_git(path, "checkout", "--force", ref)
    if checkout.returncode != 0:
        raise RuntimeError(checkout.stderr or "git checkout failed")
    new_head = _run_git(path, "rev-parse", "HEAD")
    new_ref = (new_head.stdout or "").strip() or ref
    cfg.previous_pinned_ref = cfg.pinned_ref or current_ref
    cfg.pinned_ref = new_ref
    cfg.save(update_fields=["previous_pinned_ref", "pinned_ref", "updated_at"])
    return check_update(subsystem)


def rollback_update(subsystem) -> UpdateCheckResult:
    cfg = ensure_odysseus_settings(subsystem)
    if not cfg.previous_pinned_ref:
        raise RuntimeError("no previous_pinned_ref to rollback")
    return apply_update(subsystem, cfg.previous_pinned_ref)
