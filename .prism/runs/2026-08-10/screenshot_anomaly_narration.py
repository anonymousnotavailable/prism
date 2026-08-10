"""Playwright screenshot script — Anomaly Narration feature (Run 3)."""
from playwright.sync_api import sync_playwright

BASE_URL = "http://localhost:8513"
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


def load_dataset_and_open_anomalies(page, theme=None):
    page.goto(BASE_URL, timeout=60000)
    page.wait_for_timeout(3000)
    page.click("text=Load Stocks")
    page.wait_for_timeout(4000)
    try:
        page.click("text=Got it, dismiss", timeout=3000)
        page.wait_for_timeout(500)
    except Exception:
        pass

    if theme == "light":
        page.click("text=⚙️ App Preferences")
        page.wait_for_timeout(400)
        page.locator('div[data-testid="stSelectbox"]').first.click()
        page.wait_for_timeout(400)
        page.get_by_text("Arctic (Light)", exact=True).click()
        page.wait_for_timeout(800)
        page.click("text=⚙️ App Preferences")
        page.wait_for_timeout(300)

    # Expand Anomaly Detection and run it
    page.wait_for_timeout(1000)
    locator = page.get_by_text("Anomaly Detection", exact=True)
    locator.wait_for(state="visible", timeout=8000)
    locator.click(force=True)
    page.wait_for_timeout(600)
    page.get_by_role("button", name="Find Anomalies", exact=True).first.click(force=True)
    page.wait_for_timeout(3000)
    # Click the narrate button too — no live Gemini key in this sandbox, so this
    # captures the graceful "no model available" failure state, which is itself
    # part of what Phase 4/5 asks to verify (explicit failure handling, no crash).
    try:
        page.get_by_role("button", name="Narrate these anomalies", exact=False).first.click(force=True)
        page.wait_for_timeout(1500)
    except Exception:
        pass


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROME_PATH)

        # ---- Desktop, dark theme (default) ----
        ctx = browser.new_context(viewport=VIEWPORTS["desktop"])
        page = ctx.new_page()
        load_dataset_and_open_anomalies(page)
        _scroll_main(page, 1400)
        page.screenshot(path=f"{SCREENSHOT_DIR}/anomaly_narration_desktop_dark.png", full_page=False)
        print("Captured: Anomaly Narration (desktop, dark)")
        ctx.close()

        # ---- Desktop, light theme ----
        ctx = browser.new_context(viewport=VIEWPORTS["desktop"])
        page = ctx.new_page()
        load_dataset_and_open_anomalies(page, theme="light")
        _scroll_main(page, 1400)
        page.screenshot(path=f"{SCREENSHOT_DIR}/anomaly_narration_desktop_light.png", full_page=False)
        print("Captured: Anomaly Narration (desktop, light)")
        ctx.close()

        # NOTE: no mobile (390px) capture here — this run root-caused a pre-
        # existing bug (not introduced by this feature) where Streamlit's own
        # .stVerticalBlock collapses the ENTIRE Overview tab's main content to
        # a ~22px sliver at phone widths once past the landing screen, making
        # every Overview-tab element unreadable, not just this one. See
        # .prism/audit_2026-08-10.md for the full diagnosis. A mobile
        # screenshot of this feature would just show that pre-existing bug,
        # not this feature's own layout — logged for a dedicated future fix
        # instead of captured here.

        browser.close()


if __name__ == "__main__":
    main()
