"""Diagnostic script for the mobile main-content-collapse bug logged in
.prism/audit_2026-08-10.md. Measures the main content block's rendered
width across a range of viewport widths — a fixed app should show
content_width ≈ viewport_width - (small padding), monotonically. As of
2026-08-10 it instead follows content_width ≈ viewport_width - 368 below
~768px (i.e. the collapsed/off-canvas sidebar's *expanded* width still
seems to be reserved somewhere in the layout).

Usage: boot the app (streamlit run app.py --server.port 8505), then:
  python .prism/runs/2026-08-10/diagnose_mobile_width_bug.py
"""
from playwright.sync_api import sync_playwright

BASE_URL = "http://localhost:8505"
CHROME_PATH = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
WIDTHS_TO_TEST = [390, 430, 500, 640, 700, 768, 800, 1024, 1440]


def measure(width):
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROME_PATH)
        ctx = browser.new_context(viewport={"width": width, "height": 900})
        page = ctx.new_page()
        page.goto(BASE_URL, timeout=60000)
        page.wait_for_timeout(2500)
        page.click("text=Load Sales")
        page.wait_for_timeout(3500)
        content_width = page.evaluate("""() => {
            const main = document.querySelector('div[data-testid="stMainBlockContainer"]');
            const child = main ? main.querySelector(':scope > div[data-testid="stVerticalBlock"]') : null;
            return child ? child.getBoundingClientRect().width : null;
        }""")
        browser.close()
        return content_width


if __name__ == "__main__":
    print(f"{'viewport':>10} | {'content_width':>14} | {'expected (~viewport-32)':>24}")
    for w in WIDTHS_TO_TEST:
        cw = measure(w)
        print(f"{w:>10} | {cw!s:>14} | {w - 32:>24}")
