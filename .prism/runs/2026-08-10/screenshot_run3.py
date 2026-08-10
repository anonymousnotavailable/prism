"""Playwright screenshot script for Run 3's two features:
1. Anomaly Detection AI narration (Overview tab)
2. Feature Selection Engine (ML Lab tab, behind Advanced Tools)

Desktop dark/light + mobile dark, matching prior runs' coverage pattern.
"""
from playwright.sync_api import sync_playwright

BASE_URL = "http://localhost:8501"
DIR = "/home/user/prism/.prism/runs/2026-08-10"
CHROME_PATH = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"

DESKTOP = {"width": 1440, "height": 1000}
MOBILE = {"width": 390, "height": 844}


def scroll_main(page, delta_y):
    page.evaluate(f"""
        document.querySelectorAll('section, div[data-testid="stAppViewContainer"], div[data-testid="stMain"]')
            .forEach(el => {{ el.scrollTop += {delta_y}; }});
        window.scrollBy(0, {delta_y});
    """)
    page.wait_for_timeout(400)


def open_app_and_load(page, theme_light=False, mobile=False, sample="Load Sales"):
    page.goto(BASE_URL, timeout=60000)
    page.wait_for_timeout(3000)
    if mobile:
        try:
            page.click('[data-testid="stSidebarCollapsedControl"] button', timeout=3000, force=True)
            page.wait_for_timeout(600)
        except Exception:
            pass
    if theme_light:
        try:
            page.click("text=App Preferences", timeout=8000, force=True)
            page.wait_for_timeout(600)
            page.click('[data-testid="stSelectbox"]', timeout=5000, force=True)
            page.wait_for_timeout(500)
            page.click("text=Arctic (Light)", timeout=5000, force=True)
            page.wait_for_timeout(1200)
        except Exception as e:
            print(f"  ! Theme switch failed: {e}")
    page.click(f"text={sample}", timeout=10000, force=True)
    page.wait_for_timeout(4500)
    try:
        page.click("text=Got it, dismiss", timeout=2500, force=True)
        page.wait_for_timeout(500)
    except Exception:
        pass


def open_advanced_tab(page, tab_label):
    page.wait_for_timeout(800)
    last_err = None
    for attempt in range(3):
        try:
            page.click('button:has-text("Advanced Tools")', timeout=6000, force=True)
            page.wait_for_timeout(700)
            page.click(f'button:has-text("{tab_label}")', timeout=6000, force=True)
            page.wait_for_timeout(2500)
            return
        except Exception as e:
            last_err = e
            page.wait_for_timeout(1000)
    raise last_err


def capture_anomaly_narration(page, viewport_name, theme_name):
    """Overview tab is already active after load. Open the Anomaly Detection
    expander, run detection, then trigger the AI narration.

    Uses get_by_role(..., exact=True) rather than :has-text() — Atlas's own
    "Find anomalies" suggestion chip (lowercase 'a') otherwise collides with
    the real "Find Anomalies" button inside the expander under a
    case-insensitive substring match.
    """
    try:
        page.get_by_text("Anomaly Detection", exact=True).scroll_into_view_if_needed(timeout=5000)
        page.wait_for_timeout(300)
        page.get_by_text("Anomaly Detection", exact=True).click(timeout=6000, force=True)
        page.wait_for_timeout(600)
        page.get_by_role("button", name="Find Anomalies", exact=True).click(timeout=8000, force=True)
        page.wait_for_timeout(3000)
        page.get_by_role("button", name="✨ Narrate with AI", exact=True).click(timeout=8000, force=True)
        page.wait_for_timeout(3500)
    except Exception as e:
        print(f"  ! Anomaly narration flow issue: {e}")
    scroll_main(page, 900)
    page.screenshot(path=f"{DIR}/anomaly_narration_{viewport_name}_{theme_name}.png", full_page=False)
    print(f"  captured anomaly_narration_{viewport_name}_{theme_name}")


def capture_feature_selection(page, viewport_name, theme_name):
    try:
        open_advanced_tab(page, "ML Lab")
    except Exception as e:
        print(f"  ! Could not open ML Lab: {e}")
        return
    page.wait_for_timeout(1000)
    try:
        target_select = None
        for s in page.query_selector_all('[data-testid="stSelectbox"]'):
            label = s.query_selector("label")
            if label and "Target column" in (label.inner_text() or ""):
                target_select = s
                break
        if target_select:
            target_select.scroll_into_view_if_needed(timeout=5000)
            target_select.click(force=True)
            page.wait_for_timeout(500)
            # 'region' — low-cardinality categorical column in the Sales sample,
            # keeps mutual-info/L1/RFE fast for a screenshot pass (unlike the
            # high-cardinality order_id default, which is ~1 class per row).
            page.get_by_role("option", name="region", exact=True).click(timeout=4000, force=True)
            page.wait_for_timeout(1000)
    except Exception as e:
        print(f"  ! Target column select issue: {e}")

    try:
        page.get_by_role("button", name="Rank Features", exact=True).click(timeout=8000, force=True)
        page.wait_for_timeout(4500)
    except Exception as e:
        print(f"  ! Could not run Rank Features: {e}")
        return

    scroll_main(page, 550)
    page.screenshot(path=f"{DIR}/feature_selection_{viewport_name}_{theme_name}.png", full_page=False)
    print(f"  captured feature_selection_{viewport_name}_{theme_name}")


def main():
    # Sales has zero IsolationForest-flagged rows at default contamination —
    # fine for Feature Selection (any dataset works there), but useless for
    # showing the narration button/response, which only renders when
    # something was actually flagged. Stocks has 20 flagged rows.
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROME_PATH)

        print("=== desktop / dark ===")
        ctx = browser.new_context(viewport=DESKTOP)
        page = ctx.new_page()
        open_app_and_load(page, theme_light=False, mobile=False, sample="Load Stocks")
        capture_anomaly_narration(page, "desktop", "dark")
        ctx.close()
        ctx = browser.new_context(viewport=DESKTOP)
        page = ctx.new_page()
        open_app_and_load(page, theme_light=False, mobile=False, sample="Load Sales")
        capture_feature_selection(page, "desktop", "dark")
        ctx.close()

        print("=== desktop / light ===")
        ctx = browser.new_context(viewport=DESKTOP)
        page = ctx.new_page()
        open_app_and_load(page, theme_light=True, mobile=False, sample="Load Stocks")
        capture_anomaly_narration(page, "desktop", "light")
        ctx.close()
        ctx = browser.new_context(viewport=DESKTOP)
        page = ctx.new_page()
        open_app_and_load(page, theme_light=True, mobile=False, sample="Load Sales")
        capture_feature_selection(page, "desktop", "light")
        ctx.close()

        print("=== mobile / dark ===")
        ctx = browser.new_context(viewport=MOBILE)
        page = ctx.new_page()
        open_app_and_load(page, theme_light=False, mobile=True, sample="Load Stocks")
        capture_anomaly_narration(page, "mobile", "dark")
        ctx.close()
        ctx = browser.new_context(viewport=MOBILE)
        page = ctx.new_page()
        open_app_and_load(page, theme_light=False, mobile=True, sample="Load Sales")
        capture_feature_selection(page, "mobile", "dark")
        ctx.close()

        browser.close()


if __name__ == "__main__":
    main()
