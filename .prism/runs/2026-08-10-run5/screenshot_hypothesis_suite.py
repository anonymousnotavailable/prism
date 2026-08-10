"""Playwright screenshot script — Run 5 (2026-08-10): Automated Hypothesis
Sweep panel in Stats Lab.
"""
from playwright.sync_api import sync_playwright

BASE_URL = "http://localhost:8501"
SCREENSHOT_DIR = "/home/user/prism/.prism/runs/2026-08-10-run5"
CHROME_PATH = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
CSV_PATH = "/home/user/prism/samples/hr_data.csv"

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


def load_csv(page):
    page.goto(BASE_URL, timeout=60000)
    page.wait_for_timeout(3000)
    page.set_input_files('input[type="file"]', CSV_PATH)
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


def open_stats_lab(page):
    page.click("text=⋯ Advanced Tools", timeout=5000)
    page.wait_for_timeout(400)
    page.get_by_role("button", name="🧪  Stats Lab", exact=True).click(timeout=5000)
    page.wait_for_timeout(600)
    page.keyboard.press("Escape")  # close the popover — it can otherwise stay open over the panel on mobile
    page.wait_for_timeout(600)


def run_sweep(page):
    btn = page.get_by_role("button", name="Run full sweep", exact=True)
    btn.scroll_into_view_if_needed(timeout=5000)
    btn.click(timeout=5000, force=True)
    page.wait_for_timeout(2500)


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROME_PATH)

        # ---- Desktop, dark ----
        ctx = browser.new_context(viewport=VIEWPORTS["desktop"])
        page = ctx.new_page()
        load_csv(page)
        open_stats_lab(page)
        run_sweep(page)
        _scroll_main(page, 900)
        page.screenshot(path=f"{SCREENSHOT_DIR}/01_hypothesis_sweep_desktop_dark.png", full_page=False)
        print("Captured: hypothesis sweep (desktop, dark)")
        ctx.close()

        # ---- Desktop, light ----
        ctx = browser.new_context(viewport=VIEWPORTS["desktop"])
        page = ctx.new_page()
        load_csv(page)
        switch_to_light_theme(page)
        open_stats_lab(page)
        run_sweep(page)
        _scroll_main(page, 900)
        page.screenshot(path=f"{SCREENSHOT_DIR}/02_hypothesis_sweep_desktop_light.png", full_page=False)
        print("Captured: hypothesis sweep (desktop, light)")
        ctx.close()

        # ---- Mobile, dark ----
        ctx = browser.new_context(viewport=VIEWPORTS["mobile"])
        page = ctx.new_page()
        load_csv(page)
        open_stats_lab(page)
        run_sweep(page)
        _scroll_main(page, 1200)
        page.screenshot(path=f"{SCREENSHOT_DIR}/03_hypothesis_sweep_mobile_dark.png", full_page=False)
        print("Captured: hypothesis sweep (mobile, dark)")
        ctx.close()

        # ---- Desktop dark, empty state (before running sweep) ----
        ctx = browser.new_context(viewport=VIEWPORTS["desktop"])
        page = ctx.new_page()
        load_csv(page)
        open_stats_lab(page)
        _scroll_main(page, 900)
        page.screenshot(path=f"{SCREENSHOT_DIR}/00_hypothesis_sweep_empty_state_desktop_dark.png", full_page=False)
        print("Captured: hypothesis sweep empty state (desktop, dark)")
        ctx.close()

        browser.close()


if __name__ == "__main__":
    main()
