"""Русификация оставшихся строк на главной."""
from pathlib import Path

p = Path(__file__).resolve().parents[1] / "delayu" / "templates" / "platform" / "home.html"
t = p.read_text(encoding="utf-8")
pairs = [
    ("Total Profit", "Прибыль"),
    ("Total Growth", "Рост"),
    ("Expense", "Расход"),
    ("Revenue", "Доход"),
    ("Sales", "Продажи"),
    ("Orders", "Заказы"),
    ("Customers", "Клиенты"),
    ("Visits by Day", "Визиты по дням"),
    ("Total 248.5k Visits", "Всего 248,5 тыс. визитов"),
    ("Most Visited Day", "Пиковый день"),
    ("Total 62.4k Visits on Thursday", "62,4 тыс. визитов в четверг"),
    ("Activity Timeline", "Лента активности"),
    ("12 Invoices have been paid", "Оплачено 12 счетов"),
    ("12 min ago", "12 мин назад"),
    ("Invoices have been paid to the company", "Счета оплачены контрагентом"),
    ("Client Meeting", "Встреча с клиентом"),
    ("45 min ago", "45 мин назад"),
    ("Project meeting with john @10:15am", "Совещание по проекту в 10:15"),
    ("CEO of", "Руководитель"),
    ("Create a new project for client", "Создан новый проект"),
    ("2 Day Ago", "2 дня назад"),
    ("6 team members in a project", "6 участников в проекте"),
    ("Refresh", "Обновить"),
    ("Update", "Обновить"),
    ("Share", "Поделиться"),
    ("View Report", "Отчёт"),
    ("Download", "Скачать"),
    ("Payments", "Платежи"),
    ("Order", "Заказ"),
    ("Last Month", "Прошлый месяц"),
    ("Last Year", "Прошлый год"),
    ("Blender Illustration", "Иллюстрация"),
    ("Finance App Design", "Дизайн финансового приложения"),
    ("Android Application", "Android-приложение"),
    ("Delta Web App", "Веб-приложение Delta"),
    ("eCommerce Website", "Сайт электронной коммерции"),
]
for a, b in pairs:
    t = t.replace(a, b)
p.write_text(t, encoding="utf-8")
print("updated home.html")
