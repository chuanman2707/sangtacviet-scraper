"""
Browser Manager: Handles CloakBrowser lifecycle, route abortion, and memory recycling.
"""

import os
from typing import Any, List, Optional
from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright

from config import (
    BLOCKED_URL_REGEX,
    DEFAULT_CHROMIUM_BINARY,
    DEFAULT_PAGE_TIMEOUT_MS,
    DEFAULT_RECYCLE_EVERY,
)


class BrowserManager:
    def __init__(
        self,
        headless: bool = True,
        recycle_every: int = DEFAULT_RECYCLE_EVERY,
        binary_path: Optional[str] = None,
    ):
        self.headless = headless
        self.recycle_every = recycle_every
        self.binary_path = binary_path or DEFAULT_CHROMIUM_BINARY
        
        # Ensure CloakBrowser env var is set
        os.environ["CLOAKBROWSER_BINARY_PATH"] = self.binary_path

        self._pw = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._saved_cookies: List[dict] = []
        self._chapters_since_recycle = 0

    def start(self) -> Page:
        """Start browser, create context, apply network abortion and default cookies."""
        try:
            from cloakbrowser import launch
            self._browser = launch(
                headless=self.headless,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                ],
            )
        except Exception:
            # Fallback to direct Playwright launch using the stealth binary
            self._pw = sync_playwright().start()
            self._browser = self._pw.chromium.launch(
                executable_path=self.binary_path,
                headless=self.headless,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                ],
            )

        self._create_fresh_context()
        return self._page

    def _create_fresh_context(self) -> None:
        """Create a new context, apply saved cookies and route filters."""
        if self._context:
            try:
                self._saved_cookies = self._context.cookies()
                self._context.close()
            except Exception:
                pass

        self._context = self._browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1440, "height": 900},
        )

        # Restore cookies or add required defaults
        if self._saved_cookies:
            self._context.add_cookies(self._saved_cookies)
        else:
            self._context.add_cookies([
                {"name": "lang", "value": "vi", "domain": "sangtacviet.app", "path": "/"},
                {"name": "lang", "value": "vi", "domain": "sangtacviet.vip", "path": "/"},
                {"name": "lang", "value": "vi", "domain": "sangtacviet.com", "path": "/"},
            ])

        self._page = self._context.new_page()
        self._page.set_default_timeout(DEFAULT_PAGE_TIMEOUT_MS)

        # Route Abortion: drop images, fonts, media, and third-party trackers instantly
        self._page.route(BLOCKED_URL_REGEX, lambda route: route.abort())
        self._chapters_since_recycle = 0

    def step_chapter(self) -> Page:
        """
        Notify that a chapter has been processed.
        Recycles context every `recycle_every` chapters to prevent RAM leaks.
        """
        self._chapters_since_recycle += 1
        if self._chapters_since_recycle >= self.recycle_every:
            self._create_fresh_context()
        return self._page

    @property
    def page(self) -> Page:
        if self._page is None:
            raise RuntimeError("Browser not started. Call start() first.")
        return self._page

    def close(self) -> None:
        """Gracefully release all browser resources."""
        if self._context:
            try:
                self._context.close()
            except Exception:
                pass
        if self._browser:
            try:
                self._browser.close()
            except Exception:
                pass
        if self._pw:
            try:
                self._pw.stop()
            except Exception:
                pass
