"""Generate SVG illustrations for ДелаЮ presentation (20+ images)."""
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "docs" / "presentation" / "assets" / "img"

THEMES = [
    ("01-cover", "ДелаЮ", "Платформа управления делами", "#696cff", "ri-briefcase-4-line"),
    ("02-problem", "Разрозненность", "Excel, почта, папки", "#ff4d49", "ri-error-warning-line"),
    ("03-solution", "Единый контур", "Все процессы в одном окне", "#71dd37", "ri-links-line"),
    ("04-architecture", "86 модулей", "Модульная архитектура", "#03c3ec", "ri-stack-line"),
    ("05-core", "Ядро M01–M06", "Роли, оргструктура, архив", "#696cff", "ri-settings-3-line"),
    ("06-workplace", "Рабочее место", "Кабинет, канбан, календарь", "#ffab00", "ri-dashboard-line"),
    ("07-cases", "Дела и реестры", "Карточка 360°, статусы", "#696cff", "ri-folder-3-line"),
    ("08-documents", "Документооборот", "Входящие, исходящие, журнал", "#03c3ec", "ri-mail-line"),
    ("09-bpm", "BPM", "Маршруты и согласования", "#9055fd", "ri-git-merge-line"),
    ("10-analytics", "Аналитика", "KPI, отчёты, просрочки", "#71dd37", "ri-bar-chart-box-line"),
    ("11-ai", "ИИ-слой", "OCR, поиск, ассистент", "#ff3e1d", "ri-robot-2-line"),
    ("12-integrations", "Интеграции", "API, СМЭВ, 1С, Telegram", "#8592a3", "ri-plug-line"),
    ("13-uzhv", "АИС УЖВ", "Жилищный учёт и фонд", "#03c3ec", "ri-building-4-line"),
    ("14-security", "Безопасность", "2FA, аудит, ПДн", "#ff4d49", "ri-shield-keyhole-line"),
    ("15-studio", "Studio", "Low-code настройка", "#9055fd", "ri-palette-line"),
    ("16-archive", "Архив", "Хранение и сроки", "#8592a3", "ri-archive-line"),
    ("17-calendar", "Календарь", "Сроки и события", "#ffab00", "ri-calendar-line"),
    ("18-kanban", "Канбан", "Задачи и поручения", "#71dd37", "ri-kanban-view"),
    ("19-reports", "Отчёты", "Excel, Word, PDF", "#696cff", "ri-file-chart-line"),
    ("20-deploy", "Внедрение", "Docker, PostgreSQL, Astra", "#03c3ec", "ri-server-line"),
    ("21-team", "Роли", "6 типовых ролей", "#9055fd", "ri-team-line"),
    ("22-citizen", "Граждане", "Портал обращений", "#71dd37", "ri-user-heart-line"),
]

SVG_TEMPLATE = '''<svg xmlns="http://www.w3.org/2000/svg" width="640" height="400" viewBox="0 0 640 400">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="{color}" stop-opacity="0.15"/>
      <stop offset="100%" stop-color="{color}" stop-opacity="0.04"/>
    </linearGradient>
  </defs>
  <rect width="640" height="400" rx="24" fill="url(#bg)"/>
  <rect x="40" y="40" width="120" height="120" rx="28" fill="{color}" fill-opacity="0.2"/>
  <circle cx="100" cy="100" r="48" fill="{color}" fill-opacity="0.35"/>
  <rect x="200" y="70" width="380" height="28" rx="14" fill="{color}" fill-opacity="0.25"/>
  <rect x="200" y="120" width="300" height="18" rx="9" fill="{color}" fill-opacity="0.15"/>
  <rect x="200" y="155" width="340" height="18" rx="9" fill="{color}" fill-opacity="0.12"/>
  <rect x="60" y="220" width="520" height="120" rx="16" fill="#fff" fill-opacity="0.55" stroke="{color}" stroke-opacity="0.2"/>
  <text x="320" y="265" text-anchor="middle" font-family="Segoe UI, Arial, sans-serif" font-size="28" font-weight="700" fill="#384551">{title}</text>
  <text x="320" y="305" text-anchor="middle" font-family="Segoe UI, Arial, sans-serif" font-size="18" fill="#697a8d">{subtitle}</text>
</svg>'''

OUT.mkdir(parents=True, exist_ok=True)
for slug, title, subtitle, color, _icon in THEMES:
    (OUT / f"{slug}.svg").write_text(
        SVG_TEMPLATE.format(color=color, title=title, subtitle=subtitle),
        encoding="utf-8",
    )
print("generated", len(THEMES), "images in", OUT)
