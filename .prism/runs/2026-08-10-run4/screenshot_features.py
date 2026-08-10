"""Playwright screenshot script — captures this run's three changes:
ensemble outlier detection, the Data Quality Scorecard, and the mobile
Atlas panel / light-theme table fixes, across desktop/mobile x dark/light.
"""
from playwright.sync_api import sync_playwright

BASE_URL = "http://localhost:8514"
SCREENSHOT_DIR = "/home/user/prism/.prism/runs/2026-08-10-run4"
CHROME_PATH = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"

VIEWPORTS = {
    "desktop": {"width": 1440, "height": 1000},
    "mobile": {"width": 390, "height": 844},
}


def _scroll_main(page, delta_y):
    page.evaluate(
        f"""
        document.querySelectorAll('section, div[data-testid="stAppViewContainer"], div[data-testid="stMain"]')
            .forEach(el => {{ el.scrollTop += {delta_y}; }});
        window.scrollBy(0, {delta_y});
        """
    )
    page.wait_for_timeout(400)


def load_sales_sample(page):
    page.goto(BASE_URL, timeout=60000)
    page.wait_for_timeout(3000)
    try:
        page.click("text=Load Sales", timeout=8000)
        page.wait_for_timeout(5000)
    except Exception as e:
        print(f"sample click failed: {e}")
    try:
        page.click("text=Got it, dismiss", timeout=3000)
        page.wait_for_timeout(500)
    except Exception:
        pass


def switch_to_light_theme(page):
    page.click("text=⚙️ App Preferences")
    page.wait_for_timeout(500)
    page.locator('div[data-testid="stSelectbox"]').first.click()
    page.wait_for_timeout(300)
    page.click("text=Arctic (Light)")
    page.wait_for_timeout(1500)


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROME_PATH)

        # ---- Desktop, dark: Overview with new Scorecard expander ----
        ctx = browser.new_context(viewport=VIEWPORTS["desktop"])
        page = ctx.new_page()
        load_sales_sample(page)
        page.screenshot(path=f"{SCREENSHOT_DIR}/01_overview_desktop_dark.png", full_page=False)
        print("Captured: overview landing (desktop, dark)")

        try:
            page.get_by_text("Data Quality Scorecard (export)", exact=False).click()
            page.wait_for_timeout(600)
            _scroll_main(page, 500)
            page.screenshot(path=f"{SCREENSHOT_DIR}/02_scorecard_expanded_desktop_dark.png", full_page=False)
            print("Captured: scorecard expanded (desktop, dark)")
        except Exception as e:
            print(f"scorecard expander failed: {e}")

        try:
            _scroll_main(page, 700)
            page.screenshot(path=f"{SCREENSHOT_DIR}/03_missing_outliers_tables_desktop_dark.png", full_page=False)
            print("Captured: missing/outliers themed tables (desktop, dark)")
        except Exception as e:
            print(f"table screenshot failed: {e}")

        # ---- Ensemble anomaly detection ----
        try:
            page.get_by_text("Anomaly Detection", exact=True).click()
            page.wait_for_timeout(500)
            page.click("text=🔬 Run Ensemble Detection (3 algorithms)", timeout=5000)
            page.wait_for_timeout(3000)
            _scroll_main(page, 1400)
            page.screenshot(path=f"{SCREENSHOT_DIR}/04_ensemble_detection_desktop_dark.png", full_page=False)
            print("Captured: ensemble outlier detection (desktop, dark)")
        except Exception as e:
            print(f"ensemble detection failed: {e}")
        ctx.close()

        # ---- Desktop, light theme: confirms themed-table fix ----
        ctx = browser.new_context(viewport=VIEWPORTS["desktop"])
        page = ctx.new_page()
        load_sales_sample(page)
        switch_to_light_theme(page)
        page.screenshot(path=f"{SCREENSHOT_DIR}/05_overview_desktop_light.png", full_page=False)
        try:
            _scroll_main(page, 700)
            page.screenshot(path=f"{SCREENSHOT_DIR}/06_missing_outliers_tables_desktop_light.png", full_page=False)
            print("Captured: missing/outliers themed tables (desktop, light) -- should now match light theme")
        except Exception as e:
            print(f"light table screenshot failed: {e}")
        try:
            page.get_by_text("Data Quality Scorecard (export)", exact=False).click()
            page.wait_for_timeout(600)
            page.screenshot(path=f"{SCREENSHOT_DIR}/07_scorecard_expanded_desktop_light.png", full_page=False)
            print("Captured: scorecard expanded (desktop, light)")
        except Exception as e:
            print(f"scorecard light failed: {e}")
        ctx.close()

        # ---- Mobile, dark: confirms Atlas panel no longer overlaps ----
        ctx = browser.new_context(viewport=VIEWPORTS["mobile"])
        page = ctx.new_page()
        load_sales_sample(page)
        page.screenshot(path=f"{SCREENSHOT_DIR}/08_overview_mobile_dark.png", full_page=False)
        print("Captured: overview (mobile, dark) -- Atlas panel should not overlap/squish content")
        _scroll_main(page, 900)
        page.screenshot(path=f"{SCREENSHOT_DIR}/09_scrolled_mobile_dark.png", full_page=False)
        print("Captured: scrolled overview (mobile, dark)")
        ctx.close()

        browser.close()


if __name__ == "__main__":
    main()
