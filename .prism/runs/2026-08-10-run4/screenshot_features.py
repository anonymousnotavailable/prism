"""Playwright screenshot script — captures this run's changes:
(1) Feature Selection Engine ranking table (ML Lab tab), desktop dark/light + mobile dark.
(2) Overview's Missing Values / Outliers tables now re-themed correctly in light mode
    (the light-theme dataframe styling bug fix).
"""
from playwright.sync_api import sync_playwright

BASE_URL = "http://localhost:8519"
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
        page.click("text=Load Sales", timeout=5000)
        page.wait_for_timeout(4000)
    except Exception as e:
        print(f"Sample click failed: {e}")
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


def go_to_ml_lab(page):
    adv = page.get_by_text("Advanced Tools", exact=False).first
    adv.scroll_into_view_if_needed(timeout=5000)
    adv.click(timeout=10000, force=True)
    page.wait_for_timeout(500)
    ml_lab = page.get_by_text("ML Lab", exact=False).first
    ml_lab.scroll_into_view_if_needed(timeout=5000)
    ml_lab.click(timeout=10000, force=True)
    page.wait_for_timeout(1500)


def select_revenue_target(page):
    try:
        page.locator('div[data-testid="stSelectbox"]').first.click()
        page.wait_for_timeout(300)
        page.click("text=revenue", timeout=3000)
        page.wait_for_timeout(1000)
    except Exception as e:
        print(f"Target select failed (using default target): {e}")


def run_feature_selection(page):
    select_revenue_target(page)
    try:
        page.click("text=Rank Features", timeout=5000)
        page.wait_for_timeout(3000)
    except Exception as e:
        print(f"Rank Features click failed: {e}")


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROME_PATH)

        # ---- Desktop, dark: Overview tables (fix verification) ----
        ctx = browser.new_context(viewport=VIEWPORTS["desktop"])
        page = ctx.new_page()
        load_sales_sample(page)
        _scroll_main(page, 500)
        page.screenshot(path=f"{SCREENSHOT_DIR}/01_overview_tables_desktop_dark.png", full_page=False)
        print("Captured: overview tables (desktop, dark)")

        # ---- ML Lab: Feature Selection Engine, desktop dark ----
        go_to_ml_lab(page)
        run_feature_selection(page)
        _scroll_main(page, 500)
        page.screenshot(path=f"{SCREENSHOT_DIR}/02_feature_selection_desktop_dark.png", full_page=False)
        print("Captured: feature selection ranking (desktop, dark)")
        ctx.close()

        # ---- Desktop, light theme: Overview tables + ML Lab ----
        ctx = browser.new_context(viewport=VIEWPORTS["desktop"])
        page = ctx.new_page()
        load_sales_sample(page)
        switch_to_light_theme(page)
        _scroll_main(page, 500)
        page.screenshot(path=f"{SCREENSHOT_DIR}/03_overview_tables_desktop_light.png", full_page=False)
        print("Captured: overview tables (desktop, light) — verifies the theming fix")
        go_to_ml_lab(page)
        run_feature_selection(page)
        _scroll_main(page, 500)
        page.screenshot(path=f"{SCREENSHOT_DIR}/04_feature_selection_desktop_light.png", full_page=False)
        print("Captured: feature selection ranking (desktop, light)")
        ctx.close()

        # ---- Mobile, dark ----
        ctx = browser.new_context(viewport=VIEWPORTS["mobile"])
        page = ctx.new_page()
        load_sales_sample(page)
        _scroll_main(page, 1600)
        page.screenshot(path=f"{SCREENSHOT_DIR}/05_overview_tables_mobile_dark.png", full_page=False)
        try:
            go_to_ml_lab(page)
            run_feature_selection(page)
            _scroll_main(page, 500)
            page.screenshot(path=f"{SCREENSHOT_DIR}/06_feature_selection_mobile_dark.png", full_page=False)
            print("Captured: mobile dark (overview + ML Lab)")
        except Exception as e:
            print(f"Mobile ML Lab nav unreachable (pre-existing Atlas-panel-overlap backlog issue): {e}")
        ctx.close()

        browser.close()


if __name__ == "__main__":
    main()
