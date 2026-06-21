"""Copy app-email template from Materialize django-version."""
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "delayu" / "templates" / "platform" / "correspondence" / "inbox_email_src.html"

bases = list(Path("D:/").glob("Materialize*/django-version/full-version/apps/email/templates"))
if not bases:
    bases = list(Path("D:/").glob("Materialize*/django-version/full-version/templates"))
for base in Path("D:/").rglob("app_email.html"):
    if "django-version" in str(base) and "full-version" in str(base):
        shutil.copy2(base, DEST)
        print("copied", base, "->", DEST)
        break
else:
    html = list(Path("D:/").rglob("app_email.html"))
    for p in html:
        if "vertical-menu" in str(p) or "full-version" in str(p):
            shutil.copy2(p, DEST)
            print("copied", p)
            break
    else:
        print("app_email.html not found on D:")
