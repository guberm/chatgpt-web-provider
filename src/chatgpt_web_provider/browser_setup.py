from __future__ import annotations

from pathlib import Path

from .config import Settings


def main() -> None:
    """Open a visible persistent browser profile for the first ChatGPT login."""
    settings = Settings.from_env()
    settings.headless = False
    Path(settings.profile_dir).mkdir(parents=True, exist_ok=True)

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            settings.profile_dir,
            headless=False,
            viewport={"width": 1400, "height": 1000},
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto("https://chatgpt.com/", wait_until="domcontentloaded")
        print("Log in to ChatGPT in the opened browser, select the desired model, then press Enter here to close.")
        input()
        ctx.close()


if __name__ == "__main__":
    main()
