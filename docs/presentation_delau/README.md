# Презентация «ДелаЮ» / DelaYu

Интерактивная HTML-презентация: **19 слайдов**, **12 скриншотов**, **8 hero-иллюстраций**, иконки **Lucide**.

## Версии

| Язык | HTML | PDF |
|------|------|-----|
| Русский | `index.html` | `Delayu-presentation.pdf` |
| English | `index-en.html` | `Delayu-presentation-en.pdf` |

Переключение языка — кнопка **English / Русский** в правом верхнем углу и на финальном слайде.

## Открыть

Двойной клик по нужному HTML или откройте в браузере:

- `docs/presentation/index.html`
- `docs/presentation/index-en.html`

Навигация: **← →**, **Пробел**, точки внизу, **Home** / **End**.

## Пересборка

```bash
# HTML (RU + EN)
python scripts/gen_presentation_html.py

# Скриншоты (нужен runserver :8000, admin/admin)
python scripts/capture_presentation_screenshots.py

# PDF (обе локали)
pip install pypdf
python scripts/export_presentation_pdf.py

# Только английский PDF
python scripts/export_presentation_pdf.py --lang en
```

## Ресурсы

- Скриншоты: `assets/screenshots/`
- Hero-иллюстрации: `assets/img/hero/`
- Тексты локалей: `scripts/presentation_locales.py`
