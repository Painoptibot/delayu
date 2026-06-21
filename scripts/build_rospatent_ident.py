#!/usr/bin/env python
"""
Сборка идентифицирующих материалов для Роспатента (ZIP, лимит 5 Мб).
Запуск: .venv\\Scripts\\python.exe scripts/build_rospatent_ident.py
"""
from __future__ import annotations

import zipfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "docs" / "rospatent"
LINES_EACH = 35

SOURCE_FILES = [
    "manage.py",
    "config/settings.py",
    "config/urls.py",
    "delayu/models.py",
    "delayu/urls.py",
    "delayu/views_platform.py",
    "delayu/services/bpm.py",
    "delayu/services/mail.py",
    "delayu/services/notify_dispatch.py",
]

REFERAT = """Программа для ЭВМ «ДелаЮ» (платформа «Дела.ЮГИт») предназначена для автоматизации учёта обращений, дел, документооборота, задач, согласований, отчётности и архивирования в органах власти, муниципалитетах, учреждениях и коммерческих организациях.

Программа реализует модульную web-архитектуру: единое ядро и каталог функциональных модулей, развёртываемых в подсистемах заказчика. Обеспечиваются администрирование (роли, матрица прав, организации, штатная структура), личный кабинет, реестры и карточки дел, регистрация и маршрутизация корреспонденции, BPM-согласования, документы и печатные формы, канбан и календарь, дашборды и отчёты, REST API, интеграции, аудит действий, e-mail-уведомления, маскирование ПДн и интеллектуальные сервисы. Конструкторы настраивают меню, формы, процессы и маршруты.

Тип ЭВМ: IBM PC-совместимый. ОС: Windows, Linux. Язык Python, СУБД PostgreSQL, клиент — веб-браузер."""


def fragment(path: Path) -> str:
    if not path.exists():
        return f"(файл не найден: {path})\n"
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    head = lines[:LINES_EACH]
    tail = lines[-LINES_EACH:] if len(lines) > LINES_EACH * 2 else []
    parts = [
        "=" * 72,
        f"Файл: {path.relative_to(ROOT)}",
        f"Всего строк: {len(lines)}",
        "=" * 72,
        "--- НАЧАЛО ---",
        *head,
    ]
    if tail:
        parts.extend(["", "--- КОНЕЦ ---", *tail])
    parts.append("")
    return "\n".join(parts)


def build_titul() -> str:
    return f"""ИДЕНТИФИЦИРУЮЩИЕ МАТЕРИАЛЫ
Программа для ЭВМ «ДелаЮ»
Платформа «Дела.ЮГИт»

Правообладатель (разработчик): ЮГИт
Язык реализации: Python 3
СУБД: PostgreSQL
Клиент: веб-браузер
Объём исходного текста программы: 4 Мб (без сторонних UI-библиотек)

Дата формирования: {date.today().strftime('%d.%m.%Y')}

Состав: титульный лист, реферат, фрагменты исходного текста
(начало и конец ключевых модулей платформы).
"""


def find_cyrillic_font() -> Path | None:
    candidates = [
        Path(r"C:\Windows\Fonts\arial.ttf"),
        Path(r"C:\Windows\Fonts\Arial.ttf"),
        Path(r"C:\Windows\Fonts\times.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


def build_pdf() -> Path | None:
    try:
        from fpdf import FPDF
    except ImportError:
        return None

    font = find_cyrillic_font()
    if not font:
        return None

    pdf_path = OUT_DIR / "Delayu_ident_materialy.pdf"
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=12)
    family = "Custom"
    pdf.add_font(family, "", str(font))
    pdf.add_font(family, "B", str(font))

    def section(title: str, body: str, size: int = 9):
        pdf.set_font(family, "B", 12)
        pdf.multi_cell(0, 7, title)
        pdf.ln(1)
        pdf.set_font(family, "", size)
        for line in body.splitlines():
            pdf.multi_cell(0, 4.5, line or " ")

    pdf.add_page()
    section("Идентифицирующие материалы", build_titul())
    pdf.add_page()
    section("Реферат", REFERAT, 9)
    for rel in SOURCE_FILES:
        p = ROOT / rel
        if p.exists():
            pdf.add_page()
            section(f"Исходный текст: {rel}", fragment(p), 7)

    pdf.output(str(pdf_path))
    return pdf_path


def build_zip() -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = OUT_DIR / "Delayu_ident_materialy.zip"
    files: dict[str, str] = {
        "00_titul.txt": build_titul(),
        "01_referat.txt": REFERAT,
    }
    all_frags = []
    for rel in SOURCE_FILES:
        text = fragment(ROOT / rel)
        all_frags.append(text)
        safe = rel.replace("/", "_").replace("\\", "_")
        files[f"02_src_{safe}.txt"] = text
    files["02_istochniki_svodka.txt"] = "\n".join(all_frags)

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in sorted(files.items()):
            zf.writestr(name, content.encode("utf-8"))

    return zip_path


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = build_zip()
    zsize = zip_path.stat().st_size
    print(f"ZIP: {zip_path}")
    print(f"     Размер: {zsize / 1024:.1f} KB ({zsize} байт)")
    if zsize > 5 * 1024 * 1024:
        raise SystemExit("ОШИБКА: ZIP > 5 Мб")

    pdf_path = None
    try:
        import fpdf  # noqa: F401
    except ImportError:
        print("Подсказка: pip install fpdf2 — для PDF-версии")
    else:
        try:
            pdf_path = build_pdf()
        except Exception as exc:
            print(f"PDF не создан: {exc}")
            pdf_path = None
        if pdf_path:
            psize = pdf_path.stat().st_size
            print(f"PDF: {pdf_path}")
            print(f"     Размер: {psize / 1024:.1f} KB")
            if psize > 5 * 1024 * 1024:
                print("     PDF > 5 Мб — загружайте только ZIP")

    print()
    print("=== Что загрузить в поле «Идентифицирующие материалы» ===")
    print("Файл: Delayu_ident_materialy.zip")
    print("Формат: ZIP")
    print("Содержимое: титул, реферат, фрагменты исходников (начало/конец модулей)")
    if pdf_path and pdf_path.stat().st_size <= 5 * 1024 * 1024:
        print()
        print("Альтернатива (один PDF): Delayu_ident_materialy.pdf")
    print()
    print("НЕ загружайте ZIP и PDF вместе, если суммарно > 5 Мб.")


if __name__ == "__main__":
    main()
