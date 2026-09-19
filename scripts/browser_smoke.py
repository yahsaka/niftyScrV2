"""Real Streamlit browser smoke test. Run after starting app.py in demo mode.

This is not used to claim a local Streamlit test where Streamlit isn't installed.
GitHub Actions installs the full pinned runtime and runs this script.
"""
import argparse
from pathlib import Path
import time
from urllib.request import urlopen
from playwright.sync_api import sync_playwright, expect


def wait_for_server(url: str, timeout: int = 90) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urlopen(url + "/_stcore/health", timeout=3) as response:
                if response.status == 200:
                    return
        except Exception:
            time.sleep(1)
    raise RuntimeError("Streamlit did not become healthy within the startup timeout.")


def assert_clean(page) -> None:
    # Both uncaught framework errors and domain-error UI are meaningful failures.
    expect(page.get_by_test_id("stException")).to_have_count(0)
    assert "This action could not be completed:" not in page.locator("body").inner_text()
    overflow = page.evaluate("document.documentElement.scrollWidth > window.innerWidth + 2")
    assert not overflow, "The main page overflows horizontally. Tables must scroll within their frame."


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://localhost:8501")
    parser.add_argument("--chromium", help="Optional installed Chromium executable path")
    args = parser.parse_args()
    wait_for_server(args.url)
    destination = Path("test-results")
    destination.mkdir(exist_ok=True)
    with sync_playwright() as p:
        kwargs = {"executable_path": args.chromium} if args.chromium else {}
        browser = p.chromium.launch(headless=True, **kwargs)
        page = browser.new_page(viewport={"width": 1440, "height": 1050}, device_scale_factor=1)
        page.set_default_timeout(30000)
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        try:
            page.goto(args.url, wait_until="domcontentloaded")
            expect(page.get_by_text("Your market.", exact=False)).to_be_visible()
            expect(page.get_by_text("SYNTHETIC PREVIEW", exact=False).first).to_be_visible()
            page.wait_for_timeout(1000)
            assert_clean(page)
            page.screenshot(path=str(destination / "streamlit-overview-light.png"), full_page=True)
            toggle = page.get_by_label("Dark mode", exact=True)
            toggle.check()
            page.wait_for_timeout(800)
            expect(toggle).to_be_checked()
            assert_clean(page)
            page.screenshot(path=str(destination / "streamlit-overview-dark.png"), full_page=True)
            navigation = page.locator(".st-key-navigation")
            for label in ("Screener", "Portfolio", "Paper trading", "Backtest", "Settings"):
                navigation.get_by_role("button", name=label, exact=True).click()
                page.wait_for_timeout(800)
                assert_clean(page)
            navigation.get_by_role("button", name="Screener", exact=True).click()
            search = page.get_by_label("Search company or symbol", exact=True)
            search.fill("[")
            search.press("Enter")
            expect(page.get_by_text("No matches. Nothing hidden.", exact=True)).to_be_visible()
            assert_clean(page)
            page.get_by_role("button", name="Reset filters", exact=True).click()
            page.wait_for_timeout(800)
            # Choose from the actual custom table; component events must reach Python.
            frames = page.frames
            table_frame = next((f for f in frames if "nifty_select_table" in f.url), None)
            assert table_frame is not None, "Research table component did not mount."
            table_frame.locator("tbody tr.selectable").first.click()
            expect(page.get_by_text("Model a paper position", exact=True)).to_be_visible()
            assert_clean(page)
            page.screenshot(path=str(destination / "streamlit-screener-dark.png"), full_page=True)
            navigation.get_by_role("button", name="Overview", exact=True).click()
            for width, height, label in ((768, 1024, "tablet"), (390, 844, "mobile")):
                page.set_viewport_size({"width": width, "height": height})
                page.wait_for_timeout(800)
                assert_clean(page)
                page.screenshot(path=str(destination / f"streamlit-{label}.png"), full_page=True)
            assert not errors, f"Browser JavaScript errors: {errors}"
            print("Real Streamlit browser smoke checks passed: routes, empty filter, row-to-analysis, theme, tablet and mobile.")
        except Exception:
            page.screenshot(path=str(destination / "failure.png"), full_page=True)
            (destination / "failure.html").write_text(page.content())
            raise
        finally:
            browser.close()


if __name__ == "__main__":
    main()
