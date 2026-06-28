from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from pathlib import Path

from .config import Settings
from .models import ChatMessage, CompletionResult


class Backend(ABC):
    def __init__(self, settings: Settings):
        self.settings = settings

    @abstractmethod
    async def complete(self, messages: list[ChatMessage], model: str | None = None, new_session: bool = False, level: str | None = None) -> CompletionResult:
        raise NotImplementedError

    async def health(self) -> dict:
        return {"ok": True, "backend": self.settings.backend}


class MockBackend(Backend):
    async def complete(self, messages: list[ChatMessage], model: str | None = None, new_session: bool = False, level: str | None = None) -> CompletionResult:
        last_user = next((m.text() for m in reversed(messages) if m.role == "user"), "")
        text = f"[mock:{self.settings.model_id}] {last_user}"
        return CompletionResult(text=text, model=model or self.settings.model_id, level=level, prompt_tokens=sum(len(m.text().split()) for m in messages), completion_tokens=len(text.split()))


class BrowserBackend(Backend):
    """Browser-backed ChatGPT.com worker.

    This intentionally keeps the first implementation conservative. It launches a
    persistent Chromium profile and drives ChatGPT through Playwright. Real
    production use should pin selectors with browser-level regression tests.
    """

    def __init__(self, settings: Settings):
        super().__init__(settings)
        self._lock = asyncio.Lock()
        self._playwright = None
        self._context = None
        self._page = None

    async def _ensure_page(self):
        if self._page:
            return self._page
        try:
            from playwright.async_api import async_playwright
        except Exception as exc:  # pragma: no cover - depends on optional browser env
            raise RuntimeError("playwright is not installed") from exc

        Path(self.settings.profile_dir).mkdir(parents=True, exist_ok=True)
        self._playwright = await async_playwright().start()
        self._context = await self._playwright.chromium.launch_persistent_context(
            self.settings.profile_dir,
            headless=self.settings.headless,
            viewport={"width": 1400, "height": 1000},
            args=["--disable-blink-features=AutomationControlled"],
        )
        self._page = self._context.pages[0] if self._context.pages else await self._context.new_page()
        await self._page.goto("https://chatgpt.com/", wait_until="domcontentloaded", timeout=60_000)
        return self._page

    async def complete(self, messages: list[ChatMessage], model: str | None = None, new_session: bool = False, level: str | None = None) -> CompletionResult:
        async with self._lock:
            page = await self._ensure_page()
            prompt = self._render_prompt(messages)
            if "log in" in (await page.title()).lower():
                raise RuntimeError("ChatGPT browser profile is not logged in; run setup with a visible browser first")
            if new_session:
                await self._start_new_session(page)
            await self._apply_preferences(page, model or self.settings.model_id, level)

            composer = page.locator("#prompt-textarea, div[contenteditable='true']").last
            await composer.wait_for(timeout=30_000)
            await composer.fill(prompt)
            await page.keyboard.press("Enter")
            await self._wait_until_idle(page)
            text = await self._extract_last_answer(page)
            return CompletionResult(text=text, model=model or self.settings.model_id, level=level)

    async def health(self) -> dict:
        try:
            page = await self._ensure_page()
            title = await page.title()
            return {"ok": True, "backend": "browser", "title": title, "logged_in_hint": "log in" not in title.lower()}
        except Exception as exc:
            return {"ok": False, "backend": "browser", "error": str(exc)}

    async def _apply_preferences(self, page, model: str, level: str | None) -> None:  # pragma: no cover - browser integration
        """Best-effort model / reasoning-level selection in the ChatGPT UI.

        ChatGPT UI changes often. Failure to locate a control is non-fatal: the
        request still runs with the currently selected browser model, while the
        API response records the requested model/level.
        """
        await self._try_select_label(page, self.settings.model_label(model))
        if level:
            await self._try_select_label(page, self.settings.level_label(level))

    @staticmethod
    async def _try_select_label(page, label: str) -> bool:  # pragma: no cover - browser integration
        if not label:
            return False
        candidates = (
            f"button:has-text('{label}')",
            f"[role='button']:has-text('{label}')",
            f"[role='menuitem']:has-text('{label}')",
            f"text={label}",
        )
        # First try a direct visible option (already expanded menu or direct button).
        for selector in candidates:
            try:
                loc = page.locator(selector).first
                if await loc.count() > 0 and await loc.is_visible(timeout=1000):
                    await loc.click(timeout=3000)
                    await page.wait_for_timeout(500)
                    return True
            except Exception:
                continue
        # Then try common model/menu buttons and search again.
        for opener in (
            "[data-testid='model-switcher-dropdown-button']",
            "button[aria-haspopup='menu']",
            "button:has-text('ChatGPT')",
            "button:has-text('GPT')",
        ):
            try:
                button = page.locator(opener).first
                if await button.count() > 0 and await button.is_visible(timeout=1000):
                    await button.click(timeout=3000)
                    await page.wait_for_timeout(700)
                    for selector in candidates:
                        loc = page.locator(selector).first
                        if await loc.count() > 0 and await loc.is_visible(timeout=1000):
                            await loc.click(timeout=3000)
                            await page.wait_for_timeout(500)
                            return True
            except Exception:
                continue
        return False

    @staticmethod
    def _render_prompt(messages: list[ChatMessage]) -> str:
        return "\n\n".join(f"{m.role.upper()}: {m.text()}" for m in messages)

    @staticmethod
    async def _wait_until_idle(page) -> None:  # pragma: no cover - browser integration
        stop = page.locator("button[aria-label*='Stop'], button[data-testid*='stop']")
        for _ in range(240):
            try:
                if await stop.count() == 0:
                    await page.wait_for_timeout(1500)
                    return
            except Exception:
                return
            await page.wait_for_timeout(1000)

    @staticmethod
    async def _start_new_session(page) -> None:  # pragma: no cover - browser integration
        """Move ChatGPT to a fresh conversation before sending the prompt."""
        await page.goto("https://chatgpt.com/", wait_until="domcontentloaded", timeout=60_000)
        await page.wait_for_timeout(1500)
        if await page.locator("#prompt-textarea, div[contenteditable='true']").count() > 0:
            return
        for selector in (
            "[data-testid='create-new-chat-button']",
            "button[aria-label*='New chat']",
            "a[aria-label*='New chat']",
            "a[href='/']",
        ):
            candidate = page.locator(selector).first
            try:
                if await candidate.count() > 0:
                    await candidate.click(timeout=5_000)
                    await page.wait_for_timeout(1500)
                    return
            except Exception:
                continue

    @staticmethod
    async def _extract_last_answer(page) -> str:  # pragma: no cover - browser integration
        candidates = page.locator("[data-message-author-role='assistant']")
        count = await candidates.count()
        if count == 0:
            body = await page.locator("body").inner_text(timeout=5000)
            return body[-4000:]
        return (await candidates.nth(count - 1).inner_text()).strip()


def build_backend(settings: Settings) -> Backend:
    if settings.backend == "browser":
        return BrowserBackend(settings)
    return MockBackend(settings)
