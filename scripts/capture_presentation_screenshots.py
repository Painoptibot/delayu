"""Capture real ДелаЮ screenshots for presentation."""
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8000"
OUT = Path(__file__).resolve().parents[1] / "docs" / "presentation" / "assets" / "screenshots"
OUT.mkdir(parents=True, exist_ok=True)

PAGES = [
    ("01-login", "/auth/login/", False),
    ("02-home", "/", True),
    ("03-cases", "/cases/", True),
    ("04-kanban", "/workspace/kanban/", True),
    ("05-inbox", "/correspondence/inbox/", True),
    ("06-bpm", "/bpm/approvals/", True),
    ("07-analytics", "/analytics/dashboard/", True),
    ("08-users", "/administration/users/", True),
    ("09-cabinet", "/workspace/cabinet/", True),
    ("10-calendar", "/workspace/calendar/", True),
    ("11-studio", "/studio/forms/", True),
    ("12-integrations", "/integrations/", True),
]


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1440, "height": 900},
            locale="ru-RU",
        )
        page = context.new_page()

        # Login
        page.goto(f"{BASE}/auth/login/", wait_until="networkidle", timeout=60000)
        page.screenshot(path=str(OUT / "01-login.png"), full_page=False)

        page.fill('input[name="email-username"]', "admin")
        page.fill('input[name="password"]', "admin")
        page.click('button[type="submit"]')
        page.wait_for_load_state("networkidle", timeout=60000)

        for name, path, _ in PAGES[1:]:
            url = f"{BASE}{path}"
            try:
                page.goto(url, wait_until="networkidle", timeout=45000)
                page.wait_for_timeout(800)
                page.screenshot(path=str(OUT / f"{name}.png"), full_page=False)
                print("OK", name, path)
            except Exception as exc:
                print("SKIP", name, path, exc)

        browser.close()
    print("saved to", OUT)


if __name__ == "__main__":
    main()
