"""Playwright screenshot script — captures this run's two UI changes
(Data Quality Scorecard on Overview, Feature Selection Engine on ML Lab)
across desktop/mobile x dark/light.
"""
from playwright.sync_api import sync_playwright

BASE_URL = "http://localhost:8518"
SCREENSHOT_DIR = "/home/user/prism/.prism/runs/2026-08-10-run2"
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
    try:
        page.get_by_text("How is this score calculated?", exact=False).first.wait_for(state="attached", timeout=15000)
    except Exception:
        pass
    page.wait_for_timeout(2500)
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


def open_scorecard_expander(page):
    page.get_by_text("Data Quality Scorecard", exact=False).first.click(force=True)
    page.wait_for_timeout(800)


def go_to_ml_lab(page):
    page.evaluate("window.scrollTo(0, 0); document.querySelectorAll('section, div[data-testid=\"stMain\"]').forEach(el => el.scrollTop = 0);")
    page.wait_for_timeout(400)
    page.get_by_text("Advanced Tools", exact=False).first.click(force=True)
    page.wait_for_timeout(500)
    page.get_by_text("ML Lab", exact=False).first.click(force=True)
    page.wait_for_timeout(800)
    page.keyboard.press("Escape")  # close the still-open Advanced Tools popover
    page.wait_for_timeout(700)
    # Default target (first column, "employee_id") is a bad demo pick —
    # pick "attrition" (the real classification target) instead.
    try:
        page.get_by_test_id("stMainBlockContainer").get_by_text("employee_id", exact=True).first.click(force=True)
        page.wait_for_timeout(400)
        page.get_by_role("option", name="attrition").click()
        page.wait_for_timeout(1000)
    except Exception as e:
        print(f"Target column select failed: {e}")


def run_feature_selection(page):
    try:
        page.click("text=Rank Features", timeout=5000)
        page.get_by_text("Full ranking table", exact=False).wait_for(state="visible", timeout=40000)
    except Exception as e:
        print(f"Rank Features click/wait note: {e}")
    page.wait_for_timeout(500)


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROME_PATH)

        # ---- Desktop, dark: Data Quality Scorecard ----
        ctx = browser.new_context(viewport=VIEWPORTS["desktop"])
        page = ctx.new_page()
        load_csv(page)
        open_scorecard_expander(page)
        _scroll_main(page, 300)
        page.screenshot(path=f"{SCREENSHOT_DIR}/01_quality_scorecard_desktop_dark.png", full_page=False)
        print("Captured: quality scorecard (desktop, dark)")

        # ---- Desktop, dark: Feature Selection Engine ----
        go_to_ml_lab(page)
        _scroll_main(page, 350)
        run_feature_selection(page)
        page.screenshot(path=f"{SCREENSHOT_DIR}/02_feature_selection_desktop_dark.png", full_page=False)
        print("Captured: feature selection (desktop, dark)")
        ctx.close()

        # ---- Desktop, light theme ----
        ctx = browser.new_context(viewport=VIEWPORTS["desktop"])
        page = ctx.new_page()
        load_csv(page)
        switch_to_light_theme(page)
        open_scorecard_expander(page)
        _scroll_main(page, 300)
        page.screenshot(path=f"{SCREENSHOT_DIR}/03_quality_scorecard_desktop_light.png", full_page=False)
        print("Captured: quality scorecard (desktop, light)")

        go_to_ml_lab(page)
        _scroll_main(page, 350)
        run_feature_selection(page)
        page.screenshot(path=f"{SCREENSHOT_DIR}/04_feature_selection_desktop_light.png", full_page=False)
        print("Captured: feature selection (desktop, light)")
        ctx.close()

        # ---- Mobile, dark ----
        # NOTE: the pre-existing Atlas side-panel overlap bug (flagged by
        # both 2026-08-07 runs and the earlier 2026-08-10 run, still open)
        # means the fixed-position panel consumes ~84% of a 390px viewport,
        # leaving the rest of the app — including these two new features —
        # behind an unreachable strip. This run attempted a quick media-
        # query fix and reverted it after it caused a *worse* flex-collapse
        # regression (documented in the routine log) — a real fix needs the
        # dedicated pass already on the backlog, not a patch bundled here.
        # These mobile shots document that pre-existing state (not a
        # regression from this run's changes) rather than the two features
        # themselves, consistent with how prior runs handled the same block.
        ctx = browser.new_context(viewport=VIEWPORTS["mobile"])
        page = ctx.new_page()
        load_csv(page)
        page.screenshot(path=f"{SCREENSHOT_DIR}/05_mobile_dark_landing_atlas_panel_blocker.png", full_page=False)
        print("Captured: mobile landing (dark) — documents pre-existing Atlas panel overlap blocker")
        ctx.close()

        browser.close()


if __name__ == "__main__":
    main()
