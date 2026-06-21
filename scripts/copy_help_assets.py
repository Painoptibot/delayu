"""Copy help-center header images from Materialize template if available."""
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "src" / "assets" / "img" / "pages"
DEST.mkdir(parents=True, exist_ok=True)

candidates = [
    Path(r"D:\Materialize 13.11.1 – Next.js, Vuejs, Nuxt, HTML, Laravel, Django, Asp.Net Material Design Admin Template")
    / "django-version"
    / "full-version"
    / "src"
    / "assets"
    / "img"
    / "pages",
    Path(r"D:\Materialize 13.11.1 – Next.js, Vuejs, Nuxt, HTML, Laravel, Django, Asp.Net Material Design Admin Template")
    / "html-version"
    / "full-version"
    / "assets"
    / "img"
    / "pages",
]

copied = []
for src in candidates:
    if not src.is_dir():
        continue
    for name in ("header-light.png", "header-dark.png"):
        f = src / name
        if f.is_file():
            shutil.copy2(f, DEST / name)
            copied.append(name)

if copied:
    print("Copied:", ", ".join(sorted(set(copied))))
else:
    print("Source not found; place header-light.png and header-dark.png in", DEST)
