"""Playwright screenshot script — captures the Ensemble Anomaly Detection
feature (Overview tab expander) across desktop/mobile x dark/light."""
from playwright.sync_api import sync_playwright

BASE_URL = "http://localhost:8501"
SCREENSHOT_DIR = "/home/user/prism/.prism/runs/2026-08-10"
CHROME_PATH = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"

VIEWPORTS = {
    "desktop": {"width": 1440, "height": 1000},
    "mobile": {"width": 390, "height": 844},
}


def _scroll_main(page, delta_y):
    page.evaluate(f"""
        document.querySelectorAll('section, div[data-testid="stAppViewContainer"], div[data-testid="stMain"]')
            .forEach(el => {{ el.scrollTop += {delta_y}; }});
        window.scrollBy(0, {delta_y});
    """)
    page.wait_for_timeout(400)


def load_dataset(page, label="Stocks"):
    page.goto(BASE_URL, timeout=60000)
    page.wait_for_timeout(3000)
    page.click(f"text=Load {label}")
    page.wait_for_timeout(4000)
    try:
        page.click("text=Got it, dismiss", timeout=3000)
        page.wait_for_timeout(500)
    except Exception:
        pass


def set_light_theme(page):
    # Theme lives in a selectbox inside the "App Preferences" sidebar expander.
    try:
        page.click("text=App Preferences", timeout=3000)
        page.wait_for_timeout(400)
        page.click('div[data-testid="stSelectbox"]', timeout=3000)
        page.wait_for_timeout(300)
        page.click("text=Arctic (Light)", timeout=3000)
        page.wait_for_timeout(800)
    except Exception as e:
        print("Could not switch to light theme:", e)


def open_anomaly_expander_and_scan(page):
    opened = False
    for attempt in range(4):
        try:
            locator = page.locator("text=Anomaly Detection (Ensemble)")
            locator.scroll_into_view_if_needed(timeout=8000)
            page.wait_for_timeout(400)
            locator.click(timeout=5000)
            page.wait_for_timeout(500)
            opened = True
            break
        except Exception as e:
            print(f"Attempt {attempt} to open expander failed:", e)
            page.wait_for_timeout(800)
    if not opened:
        return False
    try:
        page.click("text=Run Ensemble Anomaly Scan", timeout=5000)
        page.wait_for_timeout(3500)  # sklearn fit across 3 detectors
        _scroll_main(page, 350)  # reveal the results table + narrate/exclude buttons
        return True
    except Exception as e:
        print("Could not click scan button:", e)
        return False


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROME_PATH)

        # ---- Desktop, dark theme (default) ----
        ctx = browser.new_context(viewport=VIEWPORTS["desktop"])
        page = ctx.new_page()
        load_dataset(page)
        ok = open_anomaly_expander_and_scan(page)
        page.screenshot(path=f"{SCREENSHOT_DIR}/ensemble_anomaly_desktop_dark_v2.png", full_page=False)
        print("Captured desktop dark, scan ok =", ok)
        ctx.close()

        # ---- Desktop, light theme ----
        ctx = browser.new_context(viewport=VIEWPORTS["desktop"])
        page = ctx.new_page()
        load_dataset(page)
        set_light_theme(page)
        ok = open_anomaly_expander_and_scan(page)
        page.screenshot(path=f"{SCREENSHOT_DIR}/ensemble_anomaly_desktop_light_v2.png", full_page=False)
        print("Captured desktop light, scan ok =", ok)
        ctx.close()

        # ---- Mobile, dark theme ----
        ctx = browser.new_context(viewport=VIEWPORTS["mobile"])
        page = ctx.new_page()
        load_dataset(page)
        ok = open_anomaly_expander_and_scan(page)
        page.screenshot(path=f"{SCREENSHOT_DIR}/ensemble_anomaly_mobile_dark_v2.png", full_page=False)
        print("Captured mobile dark, scan ok =", ok)
        ctx.close()

        browser.close()


if __name__ == "__main__":
    main()
