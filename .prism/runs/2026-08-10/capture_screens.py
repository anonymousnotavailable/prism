"""Playwright screenshot script — captures this run's 2 new features
(Anomaly Narration in Overview, Feature Selection Engine in ML Lab)
across desktop/mobile x dark/light."""
import os
from playwright.sync_api import sync_playwright

BASE_URL = "http://localhost:8600"
SCREENSHOT_DIR = "/home/user/prism/.prism/runs/2026-08-10"
CHROME_PATH = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"

VIEWPORTS = {
    "desktop": {"width": 1440, "height": 1000},
    "mobile": {"width": 390, "height": 844},
}

os.makedirs(SCREENSHOT_DIR, exist_ok=True)


def _scroll_main(page, delta_y):
    page.evaluate(f"""
        document.querySelectorAll('section, div[data-testid="stAppViewContainer"], div[data-testid="stMain"]')
            .forEach(el => {{ el.scrollTop += {delta_y}; }});
        window.scrollBy(0, {delta_y});
    """)
    page.wait_for_timeout(400)


def load_dataset(page, label):
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
    try:
        page.click("text=⋯ Advanced Tools", timeout=3000)
        page.wait_for_timeout(300)
    except Exception:
        pass


def set_theme_arctic_light(page):
    try:
        page.click("text=⚙️ App Preferences", timeout=5000)
        page.wait_for_timeout(400)
        page.get_by_role("combobox").first.click(timeout=5000)
        page.wait_for_timeout(300)
        page.get_by_role("option", name="Arctic (Light)").click(timeout=3000)
        page.wait_for_timeout(1000)
        page.click("text=⚙️ App Preferences", timeout=5000)  # collapse again
        page.wait_for_timeout(300)
    except Exception as e:
        print(f"  (theme switch skipped: {e})")


def capture_anomaly_narration(page, tag):
    for _ in range(14):
        _scroll_main(page, 500)
        if page.locator("text=Anomaly Detection").count() > 1:
            break
    page.wait_for_timeout(500)
    try:
        page.locator("text=Anomaly Detection").last.click(timeout=5000)
        page.wait_for_timeout(600)
        # exact=True: the Atlas side panel has its own lowercase-'a' "Find
        # anomalies" chip — case-sensitive exact match keeps this on the
        # Anomaly Detection expander's own button instead.
        page.get_by_role("button", name="Find Anomalies", exact=True).click(timeout=5000)
        page.wait_for_timeout(2500)
        page.get_by_role("button", name="🧠 Explain these anomalies").click(timeout=5000)
        page.wait_for_timeout(2500)
    except Exception as e:
        print(f"  (anomaly flow step skipped: {e})")
    page.screenshot(path=f"{SCREENSHOT_DIR}/anomaly_narration_{tag}.png", full_page=False)
    print(f"Captured: anomaly_narration_{tag}")


def capture_feature_selection(page, tag):
    try:
        page.click("text=⋯ Advanced Tools", timeout=5000)
        page.wait_for_timeout(400)
        page.click("text=🧬  ML Lab", timeout=5000)
        page.wait_for_timeout(1500)
    except Exception as e:
        print(f"  (nav to ML Lab failed: {e})")
        return
    try:
        page.get_by_role("combobox").first.click(timeout=5000)
        page.wait_for_timeout(300)
        page.get_by_role("option", name="sector", exact=True).click(timeout=3000)
        page.wait_for_timeout(1200)
    except Exception as e:
        print(f"  (target column select skipped: {e})")
    try:
        page.click("text=Rank features", timeout=5000)
        page.wait_for_timeout(3000)
    except Exception as e:
        print(f"  (rank features click failed: {e})")
    _scroll_main(page, 500)
    page.screenshot(path=f"{SCREENSHOT_DIR}/feature_selection_{tag}.png", full_page=False)
    print(f"Captured: feature_selection_{tag}")


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROME_PATH)

        # ---- Desktop, dark theme (default) ----
        ctx = browser.new_context(viewport=VIEWPORTS["desktop"])
        page = ctx.new_page()
        load_dataset(page, "Stocks")
        capture_anomaly_narration(page, "desktop_dark")
        ctx.close()

        ctx = browser.new_context(viewport=VIEWPORTS["desktop"])
        page = ctx.new_page()
        load_dataset(page, "Startup Funding")
        capture_feature_selection(page, "desktop_dark")
        ctx.close()

        # ---- Desktop, light theme ----
        ctx = browser.new_context(viewport=VIEWPORTS["desktop"])
        page = ctx.new_page()
        load_dataset(page, "Stocks")
        set_theme_arctic_light(page)
        capture_anomaly_narration(page, "desktop_light")
        ctx.close()

        ctx = browser.new_context(viewport=VIEWPORTS["desktop"])
        page = ctx.new_page()
        load_dataset(page, "Startup Funding")
        set_theme_arctic_light(page)
        capture_feature_selection(page, "desktop_light")
        ctx.close()

        # ---- Mobile, dark theme ----
        ctx = browser.new_context(viewport=VIEWPORTS["mobile"])
        page = ctx.new_page()
        load_dataset(page, "Stocks")
        capture_anomaly_narration(page, "mobile_dark")
        ctx.close()

        browser.close()


if __name__ == "__main__":
    main()
