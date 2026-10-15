"""Проверка слоёв иллюстрации приветствия на главной."""

from django.contrib.staticfiles import finders

WELCOME_LAYER_DIR = "img/illustrations/login-layers/"
WELCOME_LAYER_FILES = ("man.png", "fx.png", "fx2.png")
DEFAULT_FIGURE = f"{WELCOME_LAYER_DIR}man.png"

# Отдельная фигура на роль, чтобы в блоке «Добро пожаловать» люди не повторялись.
_ROLE_FIGURES = {
    "uzhv_admin": "welcome-admin.png",
    "uzhv_head": "man.png",
    "uzhv_manager": "man.png",
    "uzhv_deputy": "man.png",
    "uzhv_queue_spec": "welcome-spec.png",
    "uzhv_specialist": "welcome-spec.png",
    "uzhv_appeals_spec": "welcome-spec.png",
    "uzhv_report_spec": "welcome-spec.png",
    "uzhv_orphan_spec": "welcome-orphan.png",
    "uzhv_contract_spec": "welcome-contract.png",
    "uzhv_fund_spec": "welcome-contract.png",
    "uzhv_inspector": "welcome-admin.png",
    "uzhv_viewer": "man.png",
}


def welcome_scene_ready() -> bool:
    return all(finders.find(f"{WELCOME_LAYER_DIR}{name}") for name in WELCOME_LAYER_FILES)


def welcome_figure_for_role(role_code: str) -> str:
    name = _ROLE_FIGURES.get((role_code or "").lower(), "man.png")
    path = f"{WELCOME_LAYER_DIR}{name}"
    if finders.find(path):
        return path
    return DEFAULT_FIGURE
