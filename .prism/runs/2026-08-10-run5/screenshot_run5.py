"""Playwright screenshot script — Run 5 (2026-08-10, third session):
Auto-Verified Hypothesis Testing (Auto Analyst tab) and the Feature
Selection Engine (ML Lab tab).
"""
from playwright.sync_api import sync_playwright

BASE_URL = "http://localhost:8501"
SCREENSHOT_DIR = "/home/user/prism/.prism/runs/2026-08-10-run5"
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


def load_csv(page, filename):
    page.goto(BASE_URL, timeout=60000)
    page.wait_for_timeout(3000)
    page.set_input_files('input[type="file"]', f"{SCREENSHOT_DIR}/{filename}")
    page.wait_for_timeout(4000)
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


def open_advanced_tab(page, tab_label):
    page.click("text=⋯ Advanced Tools", timeout=5000)
    page.wait_for_timeout(400)
    page.get_by_role("button", name=tab_label, exact=False).click(timeout=5000)
    page.wait_for_timeout(1200)
    # The popover stays open after the click (it doesn't auto-dismiss) and
    # sits on top of the page, blocking every widget under it — close it
    # explicitly before interacting with anything else.
    page.keyboard.press("Escape")
    page.wait_for_timeout(400)


def run_auto_analyst_and_verify(page):
    open_advanced_tab(page, "Auto Analyst")
    try:
        page.get_by_role("button", name="Run Full Analysis", exact=True).click(timeout=8000)
    except Exception as e:
        print(f"run full analysis click failed: {e}")
    page.wait_for_timeout(6000)
    try:
        page.get_by_role("button", name="⚡ Auto-verify now", exact=True).click(timeout=8000)
        page.wait_for_timeout(2000)
    except Exception as e:
        print(f"auto-verify click failed: {e}")


def run_ml_lab_feature_selection(page, target_col_text):
    open_advanced_tab(page, "ML Lab")
    try:
        page.get_by_label("Target column").click(timeout=3000)
        page.wait_for_timeout(300)
        page.get_by_role("option", name=target_col_text, exact=True).click(timeout=3000)
        page.wait_for_timeout(800)
    except Exception as e:
        print(f"target select failed: {e}")
    try:
        page.get_by_role("button", name="Rank Feature Relevance", exact=True).click(timeout=5000)
        page.wait_for_timeout(2500)
    except Exception as e:
        print(f"rank button click failed: {e}")


def shoot_hypothesis(browser):
    ctx = browser.new_context(viewport=VIEWPORTS["desktop"])
    page = ctx.new_page()
    load_csv(page, "sales_data.csv")
    run_auto_analyst_and_verify(page)
    _scroll_main(page, 500)
    page.screenshot(path=f"{SCREENSHOT_DIR}/01_hypothesis_autoverify_desktop_dark.png")
    print("Captured: hypothesis auto-verify (desktop, dark)")
    ctx.close()

    ctx = browser.new_context(viewport=VIEWPORTS["desktop"])
    page = ctx.new_page()
    load_csv(page, "sales_data.csv")
    switch_to_light_theme(page)
    run_auto_analyst_and_verify(page)
    _scroll_main(page, 500)
    page.screenshot(path=f"{SCREENSHOT_DIR}/02_hypothesis_autoverify_desktop_light.png")
    print("Captured: hypothesis auto-verify (desktop, light)")
    ctx.close()

    ctx = browser.new_context(viewport=VIEWPORTS["mobile"])
    page = ctx.new_page()
    load_csv(page, "sales_data.csv")
    run_auto_analyst_and_verify(page)
    _scroll_main(page, 900)
    page.screenshot(path=f"{SCREENSHOT_DIR}/03_hypothesis_autoverify_mobile_dark.png")
    print("Captured: hypothesis auto-verify (mobile, dark)")
    ctx.close()


def shoot_feature_selection(browser):
    ctx = browser.new_context(viewport=VIEWPORTS["desktop"])
    page = ctx.new_page()
    load_csv(page, "hr_data.csv")
    run_ml_lab_feature_selection(page, "attrition")
    page.screenshot(path=f"{SCREENSHOT_DIR}/04_feature_selection_desktop_dark.png")
    print("Captured: feature selection engine (desktop, dark)")
    ctx.close()

    ctx = browser.new_context(viewport=VIEWPORTS["desktop"])
    page = ctx.new_page()
    load_csv(page, "hr_data.csv")
    switch_to_light_theme(page)
    run_ml_lab_feature_selection(page, "attrition")
    page.screenshot(path=f"{SCREENSHOT_DIR}/05_feature_selection_desktop_light.png")
    print("Captured: feature selection engine (desktop, light)")
    ctx.close()

    ctx = browser.new_context(viewport=VIEWPORTS["mobile"])
    page = ctx.new_page()
    load_csv(page, "hr_data.csv")
    run_ml_lab_feature_selection(page, "attrition")
    page.screenshot(path=f"{SCREENSHOT_DIR}/06_feature_selection_mobile_dark.png")
    print("Captured: feature selection engine (mobile, dark)")
    ctx.close()


def main():
    import sys

    mode = sys.argv[1] if len(sys.argv) > 1 else "all"
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROME_PATH)
        if mode in ("all", "hypothesis"):
            shoot_hypothesis(browser)
        if mode in ("all", "features"):
            shoot_feature_selection(browser)
        browser.close()


if __name__ == "__main__":
    main()
