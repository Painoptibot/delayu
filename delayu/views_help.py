"""Центр помощи пользователя (шаблон help-center-landing)."""
from django.views.generic import TemplateView

from django.contrib.auth.mixins import LoginRequiredMixin

from delayu.mixins import PlatformLayoutMixin


class HelpCenterView(LoginRequiredMixin, PlatformLayoutMixin, TemplateView):
    template_name = "platform/help/center.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"] = "Центр помощи"
        ctx["help_articles"] = [
            {
                "title": "С чего начать",
                "text": "Войдите в подсистему, откройте «Личный кабинет» и «Мне на сегодня». Основные разделы — в боковом меню.",
                "icon": "ri-rocket-line",
            },
            {
                "title": "Дела и реестры",
                "text": "Реестр дел (M22) — учёт поручений. Реестры (M23) — справочники с настраиваемыми полями через конструктор форм.",
                "icon": "ri-folder-line",
            },
            {
                "title": "Документооборот",
                "text": "Входящие и исходящие, журнал регистрации, печать, ЭП и сканирование — раздел «Корреспонденция».",
                "icon": "ri-mail-line",
            },
            {
                "title": "BPM и согласования",
                "text": "Запуск процессов, задачи согласования, SLA и контроль сроков — модуль M25–M27.",
                "icon": "ri-flow-chart",
            },
            {
                "title": "Аналитика",
                "text": "KPI-дашборд, отчёты и настраиваемые виджеты на главной — модуль M15.",
                "icon": "ri-pie-chart-2-line",
            },
            {
                "title": "Интеграции",
                "text": "ЕСИА, Госключ, СМЭВ, мессенджеры — в личном кабинете, вкладка «Связи».",
                "icon": "ri-link-m",
            },
        ]
        ctx["help_topics"] = [
            {
                "category": "Рабочее место",
                "items": [
                    ("Личный кабинет", "Профиль, задачи, уведомления, настройки часового пояса."),
                    ("Календарь", "Сроки задач на месяц; фильтр «только мои»."),
                    ("Канбан и Гант", "Визуализация загрузки и этапов исполнения."),
                ],
            },
            {
                "category": "Процессы и согласования",
                "items": [
                    ("BPM", "Запуск шаблонов, решение задач согласования."),
                    ("SLA", "Контроль просрочек по правилам подсистемы."),
                ],
            },
            {
                "category": "Аналитика",
                "items": [
                    ("KPI-дашборд", "Сводка по делам, задачам и просрочкам."),
                    ("Отчёты", "Шаблоны и регламентированная отчётность."),
                ],
            },
            {
                "category": "Поддержка",
                "items": [
                    ("Демо-доступ", "admin / admin, подсистема «Пилотная»."),
                    ("Техническое задание", "Ссылка в подвале меню — полное описание модулей M01–M86."),
                ],
            },
        ]
        return ctx
