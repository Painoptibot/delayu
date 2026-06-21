"""Compare home.html content structure vs Materio index.html and home_dashboard.html."""
import re
from pathlib import Path

MATERIO = Path(
    r"D:\Materialize 13.11.1 – Next.js, Vuejs, Nuxt, HTML, Laravel, Django, Asp.Net Material Design Admin Template"
    r"\html-version\full-version\html\vertical-menu-template\index.html"
)
ROOT = Path(__file__).resolve().parents[1] / "delayu" / "templates" / "platform"


def extract_materio_content(text: str) -> str:
    m = re.search(
        r'<div class="container-xxl flex-grow-1 container-p-y">\s*(.*?)\s*</div>\s*<!-- / Content -->',
        text,
        re.S,
    )
    return m.group(1).strip() if m else ""


def extract_django_content(text: str) -> str:
    m = re.search(r"\{% block content %\}\s*(.*?)\s*\{% endblock(?: content)? %\}", text, re.S)
    return m.group(1).strip() if m else ""


def normalize(html: str) -> list[str]:
    html = html.replace("../../assets/", "STATIC/")
    html = re.sub(r"\{\{[^}]+\}\}", "VAR", html)
    html = re.sub(r"\{\%[^%]+\%\}", "", html)
    html = re.sub(r"<!--.*?-->", "", html, flags=re.S)
    lines = []
    for line in html.splitlines():
        line = line.strip()
        if line:
            lines.append(line)
    return lines


def compare(name_a: str, a: list[str], name_b: str, b: list[str], limit: int = 20) -> int:
    print(f"\n=== {name_a} vs {name_b} ===")
    print(f"lines: {len(a)} vs {len(b)}")
    diffs = 0
    for i, (x, y) in enumerate(zip(a, b)):
        if x != y:
            diffs += 1
            if diffs <= limit:
                print(f"  L{i+1}:")
                print(f"    A: {x[:140]}")
                print(f"    B: {y[:140]}")
    if len(a) != len(b):
        print(f"  length delta: {len(a) - len(b)}")
        extra = a[len(b) :] if len(a) > len(b) else b[len(a) :]
        for line in extra[:5]:
            print(f"    extra: {line[:140]}")
    print(f"  total diffs (zip): {diffs}")
    return diffs


materio = extract_materio_content(MATERIO.read_text(encoding="utf-8"))
dash = extract_django_content((ROOT / "home_dashboard.html").read_text(encoding="utf-8"))
home = extract_django_content((ROOT / "home.html").read_text(encoding="utf-8"))

ml = normalize(materio)
dl = normalize(dash)
hl = normalize(home)

compare("Materio", ml, "home_dashboard", dl)
compare("Materio", ml, "home", hl)
compare("home_dashboard", dl, "home", hl)
