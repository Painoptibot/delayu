"""
home.html из home_dashboard.html — разметка Materio 1:1.
Меняем ТОЛЬКО видимый текст и иконки (без замен в id, class, data-*).
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "delayu" / "templates" / "platform"
src = (ROOT / "home_dashboard.html").read_text(encoding="utf-8")

src = src.replace(
    "{% block title %}Dashboard - Analytics{% endblock title %}",
    "{% block title %}Главная — ДелаЮ{% endblock title %}",
)
src = src.replace("{{ COOKIES.theme|default:theme }}", "{{ theme }}")
src = src.replace(
    '<script src="{% static \'js/dashboards-analytics.js\' %}"></script>',
    '<script>window.DELAYU_DASHBOARD = {{ dashboard_json|safe }};</script>\n'
    '<script src="{% static \'js/delayu-dashboard-analytics.js\' %}"></script>',
)

# Только полные фразы / узкие HTML-контексты — НЕ трогаем id/class (Report ⊂ Reports!)
TEXT = [
    ("Congratulations <span class=\"fw-bold\">John!</span> 🎉", "Добро пожаловать, <span class=\"fw-bold\">{{ request.user.first_name|default:request.user.username }}</span>!"),
    ("You have done 68% 😎 more sales today.", "Сводка по платформе «ДелаЮ»{% if active_membership %} — {{ active_membership.subsystem.name }}{% endif %}."),
    ("Check your new badge in your profile.", "Показатели и графики за последние 30 дней."),
    ('href="javascript:;" class="btn btn-primary">View Profile', 'href="{% url \'platform-cabinet\' %}" class="btn btn-primary">Личный кабинет'),
    ('alt="View Profile"', 'alt="Профиль"'),
    ("<p>Total Orders</p>", "<p>Активных дел</p>"),
    ("<div class=\"badge bg-label-secondary rounded-pill\">Last 4 Month</div>", "<div class=\"badge bg-label-secondary rounded-pill\">Реестр дел</div>"),
    ("<span class=\"d-block card-subtitle\">Sessions</span>", "<span class=\"d-block card-subtitle\">Новые дела (тренд)</span>"),
    ("<h5 class=\"mb-0\">Total Transactions</h5>", "<h5 class=\"mb-0\">Задачи по исполнителям</h5>"),
    ("<h5 class=\"mb-1\">Report</h5>", "<h5 class=\"mb-1\">Сводка контура</h5>"),
    ("<p class=\"mb-0 card-subtitle\">Last month transactions $234.40k</p>", "<p class=\"mb-0 card-subtitle\">Текущие показатели подсистемы</p>"),
    ("<p class=\"mt-3 mb-1\">This Week</p>", "<p class=\"mt-3 mb-1\">За неделю</p>"),
    ("<p class=\"mb-1\">Performance</p>", "<p class=\"mb-1\">Эффективность</p>"),
    ('<button class="btn btn-primary" type="button">view report</button>', '<a href="{% url \'platform-overdue\' %}" class="btn btn-primary">Мониторинг сроков</a>'),
    ("<h5 class=\"mb-1\">Performance</h5>", "<h5 class=\"mb-1\">Нагрузка по направлениям</h5>"),
    ("<h5 class=\"card-title m-0 me-2\">Project Statistics</h5>", "<h5 class=\"card-title m-0 me-2\">Сводка по направлениям</h5>"),
    ("<p class=\"mb-0 fs-xsmall\">NAME</p>", "<p class=\"mb-0 fs-xsmall\">НАПРАВЛЕНИЕ</p>"),
    ("<p class=\"mb-0 fs-xsmall\">BUDGET</p>", "<p class=\"mb-0 fs-xsmall\">ПОКАЗАТЕЛЬ</p>"),
    ("<h6 class=\"mb-1\">3D Illustration</h6>", "<h6 class=\"mb-1\">Активные дела</h6>"),
    ("<small>Blender Illustration</small>", "<small>Картотека, не в архиве</small>"),
    ("<h6 class=\"mb-1\">Finance App Design</h6>", "<h6 class=\"mb-1\">Входящая корреспонденция</h6>"),
    ("<small>Figma UI Kit</small>", "<small>В работе по журналу</small>"),
    ("<h6 class=\"mb-1\">4 Square</h6>", "<h6 class=\"mb-1\">Задачи</h6>"),
    ("<small>Android Application</small>", "<small>Открытые поручения</small>"),
    ("<h6 class=\"mb-1\">Delta Web App</h6>", "<h6 class=\"mb-1\">Согласования БПМ</h6>"),
    ("<small>React Dashboard</small>", "<small>Ожидают решения</small>"),
    ("<h6 class=\"mb-1\">eCommerce Website</h6>", "<h6 class=\"mb-1\">Документы</h6>"),
    ("<small>Vue + Laravel</small>", "<small>Актуальные версии</small>"),
    ("<span class=\"d-block card-subtitle\">Total Revenue</span>", "<span class=\"d-block card-subtitle\">Новых дел за неделю</span>"),
    ("<p>Total Sales</p>", "<p>Входящих в работе</p>"),
    ("<div class=\"badge bg-label-secondary rounded-pill\">Last Six Month</div>", "<div class=\"badge bg-label-secondary rounded-pill\">Входящие</div>"),
    ("<p>Total Impression</p>", "<p>Документов в делах</p>"),
    ("<div class=\"badge bg-label-secondary rounded-pill\">Last One Year</div>", "<div class=\"badge bg-label-secondary rounded-pill\">Картотека</div>"),
    ("<span class=\"d-block card-subtitle\">Overview</span>", "<span class=\"d-block card-subtitle\">Доля исполненных дел</span>"),
    ("<h5 class=\"mb-1\">Sales Country</h5>", "<h5 class=\"mb-1\">Дела по статусам</h5>"),
    ("<p class=\"mb-0 card-subtitle\">Total $42,580 Sales</p>", "<p class=\"mb-0 card-subtitle\">Всего активных дел</p>"),
    ("<h5 class=\"card-title mb-1\">Top Referral Sources</h5>", "<h5 class=\"card-title mb-1\">Очереди по модулям</h5>"),
    ("<p class=\"card-subtitle mb-0\">Number of Sales</p>", "<p class=\"card-subtitle mb-0\">Последние записи в реестрах</p>"),
    ("<th class=\"bg-transparent border-bottom\">Product Name</th>", "<th class=\"bg-transparent border-bottom\">Наименование</th>"),
    ("<th class=\"bg-transparent border-bottom\">STATUS</th>", "<th class=\"bg-transparent border-bottom\">СТАТУС</th>"),
    ("<th class=\"text-end bg-transparent border-bottom\">Profit</th>", "<th class=\"text-end bg-transparent border-bottom\">Срок</th>"),
    ("<h5 class=\"mb-1\">Weekly Sales</h5>", "<h5 class=\"mb-1\">Динамика регистрации дел</h5>"),
    ("<p class=\"mb-0 card-subtitle\">Total 85.4k Sales</p>", "<p class=\"mb-0 card-subtitle\">За последние 30 дней</p>"),
    ("<p class=\"mb-0\">Net Income</p>", "<p class=\"mb-0\">Новых за неделю</p>"),
    ("<p class=\"mb-0\">Expense</p>", "<p class=\"mb-0\">Просрочено</p>"),
    ("<h5 class=\"mb-1\">Visits by Day</h5>", "<h5 class=\"mb-1\">Приоритет открытых задач</h5>"),
    ("<p class=\"mb-0 card-subtitle\">Total 248.5k Visits</p>", "<p class=\"mb-0 card-subtitle\">Всего открытых задач</p>"),
    ("<h6 class=\"mb-0\">Most Visited Day</h6>", "<h6 class=\"mb-0\">Просроченных задач</h6>"),
    ("<p class=\"mb-0 small\">Total 62.4k Visits on Thursday</p>", "<p class=\"mb-0 small\">Из открытых по исполнителям</p>"),
    ("<h5 class=\"mb-0\">Activity Timeline</h5>", "<h5 class=\"mb-0\">Лента активности</h5>"),
    ("<h6 class=\"mb-0\">12 Invoices have been paid</h6>", "<h6 class=\"mb-0\">Активность в контуре</h6>"),
    ("<p class=\"mb-2\">Invoices have been paid to the company</p>", "<p class=\"mb-2\">События по делам и документам</p>"),
    ("<span class=\"h6 mb-0\">invoices.pdf</span>", "<span class=\"h6 mb-0\">документ.pdf</span>"),
    ("<h6 class=\"mb-0\">Client Meeting</h6>", "<h6 class=\"mb-0\">Совещание по делу</h6>"),
    ("<p class=\"mb-2\">Project meeting with john @10:15am</p>", "<p class=\"mb-2\">Обновления в реестрах и задачах</p>"),
    ("<p class=\"mb-0 small fw-medium\">Lester McCarthy (Client)</p>", "<p class=\"mb-0 small fw-medium\">Участник процесса</p>"),
    ("<h6 class=\"mb-0\">Create a new project for client</h6>", "<h6 class=\"mb-0\">Изменение в системе</h6>"),
    ("<p class=\"mb-2\">6 team members in a project</p>", "<p class=\"mb-2\">Несколько исполнителей в деле</p>"),
    ('title="3 more"', 'title="ещё 3"'),
    ("2 Day Ago", "2 дня назад"),
    ("45 min ago", "45 мин. назад"),
    ("12 min ago", "12 мин. назад"),
    (">Google Workspace</td>", ">Служебная записка</td>"),
    (">Affiliation Program</td>", ">Поручение</td>"),
    (">Google Adsense</td>", ">Черновик ответа</td>"),
    (">facebook Adsense</td>", ">Исходящее письмо</td>"),
    (">facebook Workspace</td>", ">Дело в работе</td>"),
    (">instagram Adsense</td>", ">Корреспонденция</td>"),
    (">instagram Workspace</td>", ">Задача канбана</td>"),
    (">reddit Workspace</td>", ">Согласование БПМ</td>"),
    (">reddit Adsense</td>", ">Ожидает решения</td>"),
    (">Email Marketing Campaign</td>", ">Входящее письмо</td>"),
    (">Refresh</a>", ">Обновить</a>"),
    (">Share</a>", ">Поделиться</a>"),
    (">Update</a>", ">Обновить данные</a>"),
    (">Delete</a>", ">Скрыть</a>"),
    (">View More</a>", ">Показать ещё</a>"),
    (">Last 28 Days</a>", ">Последние 28 дней</a>"),
    (">Last Month</a>", ">Прошлый месяц</a>"),
    (">Last Year</a>", ">Прошлый год</a>"),
    ('bg-label-primary rounded-pill">Active', 'bg-label-primary rounded-pill">В работе'),
    ('bg-label-success rounded-pill">Completed', 'bg-label-success rounded-pill">Исполнено'),
    ('bg-label-info rounded-pill">In Draft', 'bg-label-info rounded-pill">Черновик'),
    ('bg-label-warning rounded-pill">warning', 'bg-label-warning rounded-pill">Внимание'),
    ('bg-label-danger rounded-pill">warning', 'bg-label-danger rounded-pill">Внимание'),
    ('bg-label-warning rounded-pill">process', 'bg-label-warning rounded-pill">В процессе'),
]

for old, new in TEXT:
    src = src.replace(old, new)

# REVENUE → ИСПОЛНИТЕЛЬ (только заголовок таблицы)
src = src.replace(
    '<th class="text-end bg-transparent border-bottom">REVENUE</th>',
    '<th class="text-end bg-transparent border-bottom">ИСПОЛНИТЕЛЬ</th>',
)

ICON_IMG = [
    ("img/icons/misc/3d-illustration.png", "ri-folder-3-line"),
    ("img/icons/misc/finance-app-design.png", "ri-mail-line"),
    ("img/icons/misc/4-square.png", "ri-checkbox-multiple-line"),
    ("img/icons/misc/delta-web-app.png", "ri-git-merge-line"),
    ("img/icons/misc/ecommerce-website.png", "ri-file-text-line"),
]
for png, icon in ICON_IMG:
    src = src.replace(
        f'<img src="{{% static \'{png}\' %}}" alt="User" class="h-25" />',
        f'<i class="icon-base {icon} icon-24px"></i>',
        1,
    )

TAB_ICONS = [
    ("google.png", "ri-folder-3-line", "primary"),
    ("facebook-rounded.png", "ri-mail-line", "info"),
    ("instagram-rounded.png", "ri-checkbox-multiple-line", "success"),
    ("reddit-rounded.png", "ri-git-merge-line", "secondary"),
]
for png, icon, color in TAB_ICONS:
    src = src.replace(
        f'<img src="{{% static \'img/icons/brands/{png}\' %}}" alt="User" />',
        f'<div class="avatar-initial bg-label-{color} rounded"><i class="icon-base {icon} icon-22px"></i></div>',
        1,
    )

src = src.replace("ri-shopping-cart-2-line", "ri-folder-3-line", 1)
src = src.replace("ri-money-dollar-circle-line", "ri-line-chart-line")

# Без символа доллара в числах и подписях
src = src.replace("$", "")

(ROOT / "home.html").write_text(src, encoding="utf-8")
print("OK", (ROOT / "home.html").stat().st_size)
