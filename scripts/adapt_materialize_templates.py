"""One-off: fix URL names in copied Materialize django templates."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "delayu" / "templates" / "platform"

REPL = [
    ("{% url 'index' %}", "{% url 'platform-home' %}"),
    ("{% url 'app-calendar' %}", "{% url 'platform-calendar' %}"),
    ("{% url 'pages-account-settings-account' %}", "{% url 'platform-cabinet' %}"),
    ("{% url 'pages-account-settings-security' %}", "{% url 'platform-cabinet-security' %}"),
    ("{% url 'pages-account-settings-billing' %}", "{% url 'platform-cabinet-billing' %}"),
    ("{% url 'pages-account-settings-notifications' %}", "{% url 'platform-cabinet-notifications' %}"),
    ("{% url 'pages-account-settings-connections' %}", "{% url 'platform-cabinet-connections' %}"),
    ("{% url 'help-center-article' %}", "{% url 'platform-help-center' %}"),
    ("{% url 'help-center-landing' %}", "{% url 'platform-help-center' %}"),
]

TARGETS = {
    "home_dashboard.html": "home.html",
    "help/center_landing_src.html": "help/center.html",
    "chat/app_chat_src.html": "chat/list.html",
    "workplace/today_src.html": "workplace/today.html",
    "admin/subsystems/list_src.html": "admin/subsystems/list.html",
    "workplace/cabinet_account_src.html": "workplace/cabinet_account.html",
    "workplace/cabinet_security_src.html": "workplace/cabinet_security.html",
    "workplace/cabinet_billing_src.html": "workplace/cabinet_billing.html",
    "workplace/cabinet_notifications_src.html": "workplace/cabinet_notifications.html",
    "workplace/cabinet_connections_src.html": "workplace/cabinet_connections.html",
}

for src_rel, dst_rel in TARGETS.items():
    src = ROOT / src_rel
    dst = ROOT / dst_rel
    if not src.exists():
        print("skip missing", src)
        continue
    text = src.read_text(encoding="utf-8")
    for old, new in REPL:
        text = text.replace(old, new)
    text = text.replace("{% load i18n %}\n", "")
    text = text.replace("{% load i18n %}", "")
    if "ДелаЮ" not in text and "{% block title %}" in text:
        text = text.replace("{% block title %}", "{% block title %}", 1)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(text, encoding="utf-8")
    print("wrote", dst)
