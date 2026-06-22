"""Проверка слоёв иллюстрации приветствия на главной."""

from django.contrib.staticfiles import finders

WELCOME_LAYER_DIR = "img/illustrations/login-layers/"
WELCOME_LAYER_FILES = ("man.png", "fx.png", "fx2.png")


def welcome_scene_ready() -> bool:
    return all(finders.find(f"{WELCOME_LAYER_DIR}{name}") for name in WELCOME_LAYER_FILES)
