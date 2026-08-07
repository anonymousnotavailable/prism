import re
import sys

from playwright.sync_api import sync_playwright

SAMPLE_CSV = "/home/user/prism/samples/stock_data.csv"
OUT = "/home/user/prism/.prism/runs/2026-08-07"
CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"


def run(theme_mode, viewport, tag):
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROME)
        page = browser.new_page(viewport=viewport)
        page.goto("http://localhost:8501", timeout=30000)
        page.wait_for_timeout(3000)

        file_input = page.locator('input[type="file"]').first
        file_input.set_input_files(SAMPLE_CSV)
        page.wait_for_timeout(5000)

        try:
            page.get_by_role("button", name="Got it, dismiss").click(timeout=3000)
            page.wait_for_timeout(500)
        except Exception:
            pass

        if theme_mode == "light":
            try:
                page.get_by_text(re.compile("App Preferences")).first.click(timeout=3000)
                page.wait_for_timeout(500)
                page.locator("div[data-baseweb='select']").first.click(timeout=3000)
                page.wait_for_timeout(500)
                page.get_by_text("Arctic (Light)", exact=True).click(timeout=3000)
                page.wait_for_timeout(1500)
            except Exception as e:
                print("theme toggle skipped:", e)

        # --- Anomaly Detection (already on Overview) ---
        try:
            page.get_by_text("Anomaly Detection", exact=True).click(timeout=5000)
            page.wait_for_timeout(500)
            page.get_by_role("button", name=re.compile("Find Anomalies")).click(timeout=5000)
            page.wait_for_timeout(4000)
            page.screenshot(path=f"{OUT}/anomaly_{tag}.png", full_page=True)
            btn = page.get_by_role("button", name=re.compile("Narrate anomalies"))
            if btn.count() > 0:
                btn.first.click(timeout=5000)
                page.wait_for_timeout(5000)
                page.screenshot(path=f"{OUT}/anomaly_narrated_{tag}.png", full_page=True)
            else:
                print("no narrate button found")
        except Exception as e:
            print("anomaly flow failed:", e)
            page.screenshot(path=f"{OUT}/anomaly_ERROR_{tag}.png", full_page=True)

        # --- Auto Analyst (behind Advanced Tools popover) ---
        try:
            page.get_by_role("button", name=re.compile("Advanced Tools")).click(timeout=5000)
            page.wait_for_timeout(500)
            page.get_by_role("button", name=re.compile(r"Auto Analyst")).click(timeout=5000)
            page.wait_for_timeout(1500)
            page.get_by_role("button", name=re.compile("Run Full Analysis")).click(timeout=5000)
            page.wait_for_timeout(20000)
            page.screenshot(path=f"{OUT}/auto_analyst_{tag}.png", full_page=True)
        except Exception as e:
            print("auto analyst flow failed:", e)
            page.screenshot(path=f"{OUT}/auto_analyst_ERROR_{tag}.png", full_page=True)

        browser.close()


if __name__ == "__main__":
    mode = sys.argv[1]
    vp = {"width": int(sys.argv[2]), "height": int(sys.argv[3])}
    tag = sys.argv[4]
    run(mode, vp, tag)
