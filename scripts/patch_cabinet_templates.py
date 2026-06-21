from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "delayu" / "templates" / "platform" / "workplace"
NAV = '{% include "platform/workplace/_cabinet_nav.html" %}\n'

for name in [
    "cabinet_account",
    "cabinet_security",
    "cabinet_billing",
    "cabinet_notifications",
    "cabinet_access",
    "cabinet_connections",
]:
    fp = ROOT / f"{name}.html"
    if name == "cabinet_notifications":
        src = ROOT / "cabinet_notifications.html"
        if not src.exists():
            src = ROOT / "cabinet_notifications_src.html"
    if not fp.exists() and name == "cabinet_access":
        notif = ROOT / "cabinet_notifications.html"
        if notif.exists():
            fp.write_text(notif.read_text(encoding="utf-8"), encoding="utf-8")
    if not fp.exists():
        print("skip", fp)
        continue
    text = fp.read_text(encoding="utf-8")
    if NAV.strip() not in text:
        text = text.replace("{% block content %}\n", "{% block content %}\n" + NAV, 1)
    text = text.replace("{% block title %}Account settings - Account{% endblock %}", "{% block title %}Личный кабинет — профиль{% endblock %}")
    text = text.replace("{% block title %}Account settings - Security{% endblock %}", "{% block title %}Личный кабинет — безопасность{% endblock %}")
    text = text.replace("{% block title %}Account settings - Billing{% endblock %}", "{% block title %}Личный кабинет — работа{% endblock %}")
    text = text.replace("{% block title %}Account settings - Notifications{% endblock %}", "{% block title %}Личный кабинет — доступ{% endblock %}")
    text = text.replace("{% block title %}Account settings - Connections{% endblock %}", "{% block title %}Личный кабинет — связи{% endblock %}")
    fp.write_text(text, encoding="utf-8")
    print("patched", fp)

acc = ROOT / "cabinet_account.html"
if acc.exists():
    t = acc.read_text(encoding="utf-8")
    start = t.find('<form id="formAccountSettings"')
    end = t.find("</form>", start) + len("</form>")
    if start > 0 and end > start:
        form_block = '''<form method="post" action="{% url 'platform-cabinet' %}" id="formAccountSettings">
          {% csrf_token %}
          <div class="row mt-1 g-5">
            {% for field in profile_form %}
            <div class="col-md-6">
              <label class="form-label" for="{{ field.id_for_label }}">{{ field.label }}</label>
              {{ field }}
              {% if field.errors %}<div class="text-danger small">{{ field.errors.0 }}</div>{% endif %}
            </div>
            {% endfor %}
          </div>
          {% if can_change %}
          <div class="mt-4">
            <button type="submit" class="btn btn-primary me-3">Сохранить</button>
            <button type="reset" class="btn btn-outline-secondary">Сброс</button>
          </div>
          {% endif %}
        </form>'''
        t = t[:start] + form_block + t[end:]
        acc.write_text(t, encoding="utf-8")
        print("patched account form")
