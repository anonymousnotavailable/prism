"""Playwright screenshot script for the 2026-08-10 run's 3 changes:
Anomaly Narration, Data Quality Scorecard, mobile Atlas panel reflow fix.
"""
from playwright.sync_api import sync_playwright

BASE_URL = "http://localhost:8505"
SCREENSHOT_DIR = "/home/user/prism/.prism/runs/2026-08-10"
CHROME_PATH = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"

VIEWPORTS = {
    "desktop": {"width": 1440, "height": 1000},
    "mobile": {"width": 390, "height": 844},
}


def load_sales_dataset(page):
    page.goto(BASE_URL, timeout=60000)
    page.wait_for_timeout(3000)
    page.click("text=Load Sales")
    page.wait_for_timeout(4000)
    try:
        page.click("text=Got it, dismiss", timeout=3000)
        page.wait_for_timeout(500)
    except Exception:
        pass


def set_theme(page, theme_label):
    try:
        page.click('[data-testid="stExpandSidebarButton"]', timeout=3000)
        page.wait_for_timeout(500)
    except Exception:
        pass
    page.click("text=⚙️ App Preferences")
    page.wait_for_timeout(400)
    page.click('div[data-testid="stSelectbox"]')
    page.wait_for_timeout(300)
    page.click(f"text={theme_label}")
    page.wait_for_timeout(800)


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROME_PATH)

        # ---- Desktop, dark: Overview -> Data Quality Scorecard expanded ----
        ctx = browser.new_context(viewport=VIEWPORTS["desktop"])
        page = ctx.new_page()
        load_sales_dataset(page)
        page.click("text=📋 Data Quality Scorecard")
        page.wait_for_timeout(1200)
        page.mouse.wheel(0, 500)
        page.wait_for_timeout(400)
        page.screenshot(path=f"{SCREENSHOT_DIR}/01_quality_scorecard_desktop_dark.png")
        print("Captured: Data Quality Scorecard (desktop, dark)")
        ctx.close()

        # ---- Desktop, dark: Anomaly Detection -> Find -> Explain ----
        ctx = browser.new_context(viewport=VIEWPORTS["desktop"])
        page = ctx.new_page()
        load_sales_dataset(page)
        page.mouse.wheel(0, 1400)
        page.wait_for_timeout(400)
        page.get_by_text("Anomaly Detection", exact=True).click()
        page.wait_for_timeout(600)
        page.get_by_role("button", name="Find Anomalies", exact=True).click()
        page.wait_for_timeout(2500)
        page.mouse.wheel(0, 400)
        page.wait_for_timeout(400)
        page.screenshot(path=f"{SCREENSHOT_DIR}/02_anomaly_narration_button_desktop_dark.png")
        print("Captured: Anomaly Detection w/ Explain button (desktop, dark)")
        ctx.close()

        # ---- Desktop, light (Arctic): Data Quality Scorecard ----
        ctx = browser.new_context(viewport=VIEWPORTS["desktop"])
        page = ctx.new_page()
        load_sales_dataset(page)
        set_theme(page, "Arctic (Light)")
        page.click("text=📋 Data Quality Scorecard")
        page.wait_for_timeout(1200)
        page.mouse.wheel(0, 500)
        page.wait_for_timeout(400)
        page.screenshot(path=f"{SCREENSHOT_DIR}/03_quality_scorecard_desktop_light.png")
        print("Captured: Data Quality Scorecard (desktop, light)")
        ctx.close()

        # ---- Mobile, dark: Atlas panel reflow (scroll to bottom to see it in-flow) ----
        ctx = browser.new_context(viewport=VIEWPORTS["mobile"])
        page = ctx.new_page()
        load_sales_dataset(page)
        page.screenshot(path=f"{SCREENSHOT_DIR}/04a_mobile_dark_top.png")
        page.mouse.wheel(0, 1800)
        page.wait_for_timeout(500)
        page.screenshot(path=f"{SCREENSHOT_DIR}/04b_mobile_dark_scrolled_to_atlas.png")
        print("Captured: mobile dark top + scrolled-to-Atlas")
        ctx.close()

        # ---- Mobile, light: same scroll-to-Atlas check ----
        ctx = browser.new_context(viewport=VIEWPORTS["mobile"])
        page = ctx.new_page()
        load_sales_dataset(page)
        set_theme(page, "Arctic (Light)")
        page.mouse.wheel(0, 1800)
        page.wait_for_timeout(500)
        page.screenshot(path=f"{SCREENSHOT_DIR}/05_mobile_light_scrolled_to_atlas.png")
        print("Captured: mobile light scrolled-to-Atlas")
        ctx.close()

        browser.close()


if __name__ == "__main__":
    main()
