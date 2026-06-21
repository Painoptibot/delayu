"""Export presentation to PDF — one PDF page per slide (RU + EN)."""
import argparse
import tempfile
from pathlib import Path

from playwright.sync_api import sync_playwright

try:
    from pypdf import PdfWriter
except ImportError:
    PdfWriter = None

ROOT = Path(__file__).resolve().parents[1] / "docs" / "presentation"

LOCALES = {
    "ru": {"html": "index.html", "pdf": "Delayu-presentation.pdf"},
    "en": {"html": "index-en.html", "pdf": "Delayu-presentation-en.pdf"},
}

PREPARE_JS = """
() => {
  document.querySelector('.nav')?.style.setProperty('display', 'none', 'important');
  document.querySelector('.bg-live')?.style.setProperty('display', 'none', 'important');
  document.querySelector('.lang-switch')?.style.setProperty('display', 'none', 'important');
  const deck = document.querySelector('.deck');
  if (deck) {
    deck.style.height = '210mm';
    deck.style.maxHeight = '210mm';
    deck.style.overflow = 'hidden';
    deck.style.position = 'static';
  }
  document.documentElement.style.overflow = 'hidden';
  document.documentElement.style.height = '210mm';
  document.body.style.overflow = 'hidden';
  document.body.style.height = '210mm';
  document.body.style.background = '#fff';
  if (window.lucide) lucide.createIcons();
}
"""

SHOW_SLIDE_JS = """
(idx) => {
  const slides = [...document.querySelectorAll('.slide')];
  slides.forEach((slide, j) => {
    const on = j === idx;
    slide.style.setProperty('display', on ? 'flex' : 'none', 'important');
    if (!on) return;
    slide.style.setProperty('position', 'relative', 'important');
    slide.style.setProperty('inset', 'auto', 'important');
    slide.style.setProperty('height', '190mm', 'important');
    slide.style.setProperty('max-height', '190mm', 'important');
    slide.style.setProperty('min-height', '0', 'important');
    slide.style.setProperty('width', '100%', 'important');
    slide.style.setProperty('box-sizing', 'border-box', 'important');
    slide.style.setProperty('padding', '8mm 10mm', 'important');
    slide.style.setProperty('overflow', 'hidden', 'important');
    slide.style.setProperty('animation', 'none', 'important');
    slide.style.setProperty('page-break-after', 'avoid', 'important');
    slide.style.setProperty('break-after', 'avoid', 'important');
    if (!slide.classList.contains('slide--cover')) {
      slide.style.setProperty(
        'background',
        'linear-gradient(165deg,#ffffff 0%,#f8f9fc 48%,#f1f4f8 100%)',
        'important'
      );
    }
  });
}
"""


def export_single_pdf(page, path: Path) -> None:
    page.pdf(
        path=str(path),
        width="297mm",
        height="210mm",
        print_background=True,
        margin={"top": "0", "bottom": "0", "left": "0", "right": "0"},
    )


def export_locale(locale: str) -> None:
    if PdfWriter is None:
        raise SystemExit("Install pypdf: pip install pypdf")

    cfg = LOCALES[locale]
    html = ROOT / cfg["html"]
    pdf = ROOT / cfg["pdf"]
    url = html.resolve().as_uri()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.goto(url, wait_until="domcontentloaded", timeout=90000)
        page.wait_for_timeout(2500)
        page.evaluate(PREPARE_JS)
        page.wait_for_timeout(400)

        slide_count = page.locator(".slide").count()
        writer = PdfWriter()

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            for i in range(slide_count):
                page.evaluate(SHOW_SLIDE_JS, i)
                page.wait_for_timeout(350)
                chunk = tmp_path / f"slide-{i:02d}.pdf"
                export_single_pdf(page, chunk)
                writer.append(str(chunk))

            with pdf.open("wb") as out:
                writer.write(out)

        browser.close()

    print(f"OK [{locale}] {pdf} slides={slide_count} bytes={pdf.stat().st_size}")


def main():
    parser = argparse.ArgumentParser(description="Export DelaYu presentation PDF")
    parser.add_argument(
        "--lang",
        choices=("ru", "en", "all"),
        default="all",
        help="Locale to export (default: all)",
    )
    args = parser.parse_args()
    locales = ("ru", "en") if args.lang == "all" else (args.lang,)
    for locale in locales:
        export_locale(locale)


if __name__ == "__main__":
    main()
