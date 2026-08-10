"""Playwright screenshot script — Anomaly Detection panel (LOF method
selector + narration button), desktop/mobile x dark/light."""
from playwright.sync_api import sync_playwright

BASE_URL = "http://localhost:8511"
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


def _scroll_main(page, delta_y):
    # mouse.wheel scrolls the outer window, which doesn't move Streamlit's
    # internal scroll container on narrow (mobile) viewports — scroll the
    # actual app container via JS instead, matching the 2026-08-07 script.
    page.evaluate(
        f"""
        document.querySelectorAll('section, div[data-testid="stAppViewContainer"], div[data-testid="stMain"]')
            .forEach(el => {{ el.scrollTop += {delta_y}; }});
        window.scrollBy(0, {delta_y});
    """
    )
    page.wait_for_timeout(300)


def open_anomaly_panel(page):
    # Expand the "Anomaly Detection" expander inside the Overview tab.
    # Streamlit reruns the DOM on every interaction, which invalidates
    # locator handles held across a wait — re-query fresh right before each
    # action instead of caching a handle. Viewport width affects how much
    # content stacks above the expander, so scroll incrementally and stop
    # as soon as the target is actually reachable instead of a fixed amount.
    locator = page.get_by_text("Anomaly Detection", exact=True).last
    for _ in range(14):
        try:
            locator.click(timeout=1500, force=True)
            page.wait_for_timeout(600)
            return
        except Exception:
            _scroll_main(page, 250)
    # last-ditch attempt, let the real error surface if this also fails
    locator.click(timeout=15000, force=True)
    page.wait_for_timeout(600)


def switch_theme_light(page):
    # Sidebar "⚙️ App Preferences" expander → "Theme" selectbox. Only
    # "Arctic (Light)" is a light theme among the 6 options.
    page.get_by_text("App Preferences", exact=False).first.click(timeout=10000, force=True)
    page.wait_for_timeout(400)
    for attempt in range(4):
        page.locator('div[data-baseweb="select"]').first.click(timeout=10000, force=True)
        page.wait_for_timeout(500)
        option = page.locator('li[role="option"]', has_text="Arctic")
        try:
            option.click(timeout=3000, force=True)
            break
        except Exception:
            page.wait_for_timeout(400)
    page.wait_for_timeout(600)


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROME_PATH)

        # ---- Desktop, dark (default) ----
        ctx = browser.new_context(viewport=VIEWPORTS["desktop"])
        page = ctx.new_page()
        load_sales_dataset(page)
        open_anomaly_panel(page)
        page.screenshot(path=f"{SCREENSHOT_DIR}/anomaly_method_selector_desktop_dark.png")
        page.locator("button", has_text="Find Anomalies").last.click(force=True)
        page.wait_for_timeout(2500)
        page.screenshot(path=f"{SCREENSHOT_DIR}/anomaly_flagged_isolation_forest_desktop_dark.png")
        print("Captured: Anomaly Detection, Isolation Forest (desktop, dark)")

        # switch to LOF and re-run — Streamlit's selectbox is a BaseWeb
        # combobox, not a native <select>; open it, then click the option.
        # Retry the open+select pair since the popover occasionally doesn't
        # register the first click (same flakiness Run 2 documented).
        for attempt in range(4):
            page.locator('div[data-baseweb="select"]').last.click(timeout=10000, force=True)
            page.wait_for_timeout(500)
            option = page.locator('li[role="option"]', has_text="Local Outlier Factor")
            try:
                option.click(timeout=3000, force=True)
                break
            except Exception:
                page.wait_for_timeout(400)
        page.wait_for_timeout(500)
        page.locator("button", has_text="Find Anomalies").last.click(force=True)
        page.wait_for_timeout(2500)
        page.screenshot(path=f"{SCREENSHOT_DIR}/anomaly_flagged_lof_desktop_dark.png")
        print("Captured: Anomaly Detection, LOF (desktop, dark)")
        ctx.close()

        # ---- Desktop, light ----
        ctx = browser.new_context(viewport=VIEWPORTS["desktop"])
        page = ctx.new_page()
        load_sales_dataset(page)
        switch_theme_light(page)
        open_anomaly_panel(page)
        page.locator("button", has_text="Find Anomalies").last.click(force=True)
        page.wait_for_timeout(2500)
        page.screenshot(path=f"{SCREENSHOT_DIR}/anomaly_flagged_desktop_light.png")
        print("Captured: Anomaly Detection (desktop, light)")
        ctx.close()

        # ---- Mobile, dark ----
        # NOTE: at 390px the pre-existing Atlas panel reflow bug (logged by
        # Run 2, .prism/routine_log.md 2026-08-07) squeezes main content
        # into an unreadable strip and the panel isn't reachable by
        # scrolling. Not this feature's fault and out of scope to fix here
        # (deliberately deferred, needs its own CSS pass) — capture the
        # top-of-page state as evidence it's still present, don't force it.
        ctx = browser.new_context(viewport=VIEWPORTS["mobile"])
        page = ctx.new_page()
        load_sales_dataset(page)
        page.screenshot(path=f"{SCREENSHOT_DIR}/mobile_dark_top_atlas_reflow_bug_still_present.png")
        print("Captured: mobile top (reconfirms pre-existing Atlas reflow bug, not a regression)")
        ctx.close()

        browser.close()


if __name__ == "__main__":
    main()
