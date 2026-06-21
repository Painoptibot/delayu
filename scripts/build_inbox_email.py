"""Собрать inbox.html из Materialize app_email + Django."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "delayu" / "templates" / "platform" / "correspondence"
src = (ROOT / "inbox_email_src.html").read_text(encoding="utf-8")

RU = [
    ("{% load i18n %}\n", ""),
    ("Email - Apps", "Корреспонденция — ДелаЮ"),
    ("Compose", "Регистрация"),
    ("Inbox", "Входящие"),
    ("Sent", "Исходящие"),
    ("Draft", "Черновики"),
    ("Starred", "Избранное"),
    ("Spam", "Спам"),
    ("Trash", "Корзина"),
    ("Labels", "Метки"),
    ("Personal", "Личное"),
    ("Company", "Служебное"),
    ("Important", "Важное"),
    ("Private", "Конфиденциально"),
    ("Search mail", "Поиск по почте"),
    ("Mark as read", "Пометить прочитанным"),
    ("Mark as unread", "Пометить непрочитанным"),
    ("Delete", "Удалить"),
    ("Archive", "В архив"),
    ("Workshop", "Совещание"),
    ("Refresh", "Обновить"),
    ("Update", "Обновить"),
    ("Share", "Поделиться"),
    ("No items found.", "Ничего не найдено"),
]

for a, b in RU:
    src = src.replace(a, b)

src = re.sub(
    r'<button class="btn btn-primary btn-compose"[^>]*>.*?</button>',
    '<a href="{% url \'platform-correspondence-inbound\' %}" class="btn btn-primary btn-compose w-100">Регистрация входящего</a>',
    src,
    count=1,
)

# Sidebar folders
src = re.sub(
    r'<li class="active d-flex justify-content-between align-items-center mb-1" data-target="inbox">.*?</li>',
    """<li class="{% if mail_folder == 'inbox' %}active {% endif %}d-flex justify-content-between align-items-center mb-1" data-target="inbox">
            <a href="{% url 'platform-inbox' %}?folder=inbox" class="d-flex flex-wrap align-items-center">
              <i class="icon-base ri ri-mail-line me-1"></i>
              <span class="align-middle ms-2">Входящие</span>
            </a>
          </li>""",
    src,
    count=1,
    flags=re.DOTALL,
)
src = re.sub(
    r'<li class="d-flex mb-1" data-target="sent">.*?</li>',
    """<li class="{% if mail_folder == 'sent' %}active {% endif %}d-flex mb-1" data-target="sent">
            <a href="{% url 'platform-inbox' %}?folder=sent" class="d-flex flex-wrap align-items-center">
              <i class="icon-base ri ri-send-plane-line me-1"></i>
              <span class="align-middle ms-2">Исходящие</span>
            </a>
          </li>""",
    src,
    count=1,
    flags=re.DOTALL,
)
src = re.sub(
    r'<li class="d-flex justify-content-between align-items-center mb-1" data-target="draft">.*?</li>',
    """<li class="{% if mail_folder == 'draft' %}active {% endif %}d-flex justify-content-between align-items-center mb-1" data-target="draft">
            <a href="{% url 'platform-inbox' %}?folder=draft" class="d-flex flex-wrap align-items-center">
              <i class="icon-base ri ri-edit-box-line me-1"></i>
              <span class="align-middle ms-2">Черновики</span>
            </a>
          </li>""",
    src,
    count=1,
    flags=re.DOTALL,
)
src = re.sub(
    r'<li class="d-flex justify-content-between mb-1" data-target="starred">.*?</li>',
    """<li class="{% if mail_folder == 'starred' %}active {% endif %}d-flex justify-content-between mb-1" data-target="starred">
            <a href="{% url 'platform-inbox' %}?folder=starred" class="d-flex flex-wrap align-items-center">
              <i class="icon-base ri ri-star-line me-1"></i>
              <span class="align-middle ms-2">Избранное</span>
            </a>
          </li>""",
    src,
    count=1,
    flags=re.DOTALL,
)
src = re.sub(
    r'<li class="d-flex justify-content-between align-items-center mb-1" data-target="spam">.*?</li>',
    """<li class="{% if mail_folder == 'spam' %}active {% endif %}d-flex justify-content-between align-items-center mb-1" data-target="spam">
            <a href="{% url 'platform-inbox' %}?folder=spam" class="d-flex flex-wrap align-items-center">
              <i class="icon-base ri ri-spam-2-line me-1"></i>
              <span class="align-middle ms-2">Спам</span>
            </a>
          </li>""",
    src,
    count=1,
    flags=re.DOTALL,
)
src = re.sub(
    r'<li class="d-flex align-items-center" data-target="trash">.*?</li>',
    """<li class="{% if mail_folder == 'trash' %}active {% endif %}d-flex align-items-center" data-target="trash">
            <a href="{% url 'platform-inbox' %}?folder=trash" class="d-flex flex-wrap align-items-center">
              <i class="icon-base ri ri-delete-bin-7-line me-1"></i>
              <span class="align-middle ms-2">Корзина</span>
            </a>
          </li>""",
    src,
    count=1,
    flags=re.DOTALL,
)

# Label filters -> data-mail-action
src = src.replace(
    '<a href="javascript:void(0);">\n                <i class="badge badge-dot bg-success"></i>\n                <span class="align-middle ms-2">Личное</span>',
    '<a href="javascript:void(0);" data-mail-action="label" data-mail-label="work">\n                <i class="badge badge-dot bg-success"></i>\n                <span class="align-middle ms-2">Личное</span>',
    1,
)
src = src.replace(
    '<a href="javascript:void(0);">\n                <i class="badge badge-dot bg-primary"></i>\n                <span class="align-middle ms-2">Служебное</span>',
    '<a href="javascript:void(0);" data-mail-action="label" data-mail-label="company">\n                <i class="badge badge-dot bg-primary"></i>\n                <span class="align-middle ms-2">Служебное</span>',
    1,
)
src = src.replace(
    '<a href="javascript:void(0);">\n                <i class="badge badge-dot bg-warning"></i>\n                <span class="align-middle ms-2">Важное</span>',
    '<a href="javascript:void(0);" data-mail-action="label" data-mail-label="important">\n                <i class="badge badge-dot bg-warning"></i>\n                <span class="align-middle ms-2">Важное</span>',
    1,
)
src = src.replace(
    '<a href="javascript:void(0);">\n                <i class="badge badge-dot bg-danger"></i>\n                <span class="align-middle ms-2">Конфиденциально</span>',
    '<a href="javascript:void(0);" data-mail-action="label" data-mail-label="private">\n                <i class="badge badge-dot bg-danger"></i>\n                <span class="align-middle ms-2">Конфиденциально</span>',
    1,
)

# Toolbar dropdowns
for old, act in [
    ("Пометить прочитанным", "mark_read"),
    ("Пометить непрочитанным", "mark_unread"),
    ("Удалить", "delete"),
]:
    src = src.replace(
        f'<a class="dropdown-item" href="javascript:void(0)">{old}</a>',
        f'<a class="dropdown-item" href="javascript:void(0)" data-mail-action="{act}">{old}</a>',
        1,
    )

list_start = src.index('<div class="email-list pt-0">')
list_end = src.index("<!-- /Emails List -->")
view_start = src.index("    <!-- Email View -->", list_end)
view_end = src.index("\n  </div>", view_start) + len("\n  </div>")

items_tpl = r"""<div class="email-list pt-0">
          <ul class="list-unstyled m-0">
            {% for c in items %}
            <li class="email-list-item d-flex align-items-center{% if c.is_read %} email-marked-read{% endif %}"
                data-bs-toggle="sidebar"
                data-target="#app-email-view"
                data-corr-pk="{{ c.pk }}"
                data-panel-url="{% url 'platform-correspondence-panel' c.pk %}"
                data-starred="{% if c.is_starred %}true{% else %}false{% endif %}"
                {% if c.mail_label %}data-{{ c.mail_label }}="true"{% endif %}>
              <div class="d-flex align-items-center w-100">
                <div class="form-check mb-0 ms-2 mt-1" onclick="event.stopPropagation()">
                  <input class="email-list-item-input form-check-input" type="checkbox" id="email-{{ c.pk }}" />
                  <label class="form-check-label" for="email-{{ c.pk }}"></label>
                </div>
                <span class="ms-sm-2 me-3 d-sm-inline-block d-none"><i class="email-list-item-bookmark icon-base ri {% if c.is_starred %}ri-star-fill{% else %}ri-star-line{% endif %} icon-22px cursor-pointer"></i></span>
                <div class="avatar avatar-sm d-block flex-shrink-0 me-sm-2 me-0">
                  <span class="avatar-initial rounded-circle bg-label-secondary delayu-pii">{{ c.counterparty|slice:":2"|upper|default:"?" }}</span>
                </div>
                <div class="email-list-item-content ms-2 ms-sm-0 me-2">
                  <span class="email-list-item-username me-2 text-heading delayu-pii">{{ c.counterparty|truncatechars:24|default:"—" }}</span>
                  <small class="email-list-item-subject d-xl-inline-block d-block delayu-pii">{{ c.subject|truncatechars:60 }}</small>
                </div>
                <div class="email-list-item-meta ms-auto d-flex align-items-center">
                  {% if c.mail_label %}<span class="email-list-item-label badge badge-dot bg-{% if c.mail_label == 'important' %}warning{% elif c.mail_label == 'private' %}danger{% elif c.mail_label == 'company' %}primary{% else %}success{% endif %} d-none d-md-inline-block me-2"></span>{% endif %}
                  <span class="badge bg-label-secondary me-2 d-none d-md-inline-block">{{ c.get_status_display }}</span>
                  <small class="email-list-item-time text-body-secondary">{{ c.reg_date|date:"d.m" }}</small>
                  <ul class="list-inline email-list-item-actions">
                    <li class="list-inline-item email-delete btn btn-icon btn-text-secondary rounded-pill"><i class="icon-base ri ri-delete-bin-7-line icon-22px"></i></li>
                    <li class="list-inline-item {% if c.is_read %}email-read{% else %}email-unread{% endif %} btn btn-icon btn-text-secondary rounded-pill"><i class="icon-base ri {% if c.is_read %}ri-mail-open-line{% else %}ri-mail-line{% endif %} icon-22px"></i></li>
                    <li class="list-inline-item btn btn-icon btn-text-secondary rounded-pill"><a href="{% url 'platform-correspondence-detail' c.pk %}" class="text-body" onclick="event.stopPropagation()"><i class="icon-base ri ri-information-line icon-22px"></i></a></li>
                  </ul>
                </div>
              </div>
            </li>
            {% empty %}
            <li class="p-5 text-center text-muted">Нет писем в этой папке</li>
            {% endfor %}
          </ul>
          <ul class="list-unstyled m-0">
            <li class="email-list-empty text-center d-none">Ничего не найдено</li>
          </ul>
        </div>
      </div>
      <div class="app-overlay"></div>
    </div>
    <!-- /Emails List -->

    <!-- Email View -->
    <div class="col app-email-view flex-grow-0 bg-lightest" id="app-email-view"{% if request.GET.open %} data-open-pk="{{ request.GET.open }}"{% endif %}>
      <div class="card shadow-none border-0 rounded-0 app-email-view-header p-5 pt-md-4 py-2">
        <div class="d-flex justify-content-between align-items-center">
          <div class="d-flex align-items-center overflow-hidden">
            <span class="ms-sm-2 me-4"><i class="icon-base ri ri-arrow-left-s-line icon-22px cursor-pointer scaleX-n1-rtl" data-bs-toggle="sidebar" data-target="#app-email-view"></i></span>
            <h6 class="text-truncate mb-0 me-2 fw-normal" id="delayuEmailViewTitle">Выберите письмо</h6>
            <span class="badge bg-label-secondary rounded-pill d-none" id="delayuEmailViewBadge"></span>
          </div>
        </div>
        <hr class="app-email-view-hr mx-n5 mb-2" />
      </div>
      <hr class="m-0" />
      <div class="app-email-view-content py-4" id="delayuEmailViewContent">
        <p class="text-center text-muted py-6 mb-0">Выберите письмо в списке слева</p>
      </div>
    </div>
    <!-- /Email View -->"""

src = src[:list_start] + items_tpl + src[view_end:]

src = re.sub(
    r'<div class="app-email-compose modal".*?</div>\s*</div>\s*</div>\s*</div>',
    "",
    src,
    count=1,
    flags=re.DOTALL,
)

src = src.replace(
    "{% block content %}\n<div class=\"app-email card\">",
    "{% block content %}\n{% include \"platform/correspondence/_nav.html\" %}\n"
    "{% csrf_token %}\n"
    '<form method="get" class="d-none" id="corrFilterForm"><input type="hidden" name="q" value="{{ search_q }}"><input type="hidden" name="status" value="{{ filter_status }}"><input type="hidden" name="folder" value="{{ mail_folder }}"></form>\n'
    '<div class="app-email card" data-actions-url="{% url \'platform-correspondence-actions\' %}">',
    1,
)

src = src.replace(
    "{% block page_js %}\n{{ block.super }}\n<script src=\"{% static 'js/app-email.js' %}\"></script>",
    "{% block page_js %}\n{{ block.super }}\n<script src=\"{% static 'js/app-email.js' %}\"></script>\n"
    "<script src=\"{% static 'js/delayu-correspondence-mail.js' %}\"></script>",
    1,
)

(ROOT / "inbox.html").write_text(src, encoding="utf-8")
print("wrote", ROOT / "inbox.html")
