"""
Browser Manager: Handles CloakBrowser lifecycle, route abortion, and memory recycling.
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright

from config import (
    ALLOWED_DOMAINS,
    BLOCKED_URL_REGEX,
    DEFAULT_CHROMIUM_BINARY,
    DEFAULT_COOKIES_FILE,
    DEFAULT_PAGE_TIMEOUT_MS,
    DEFAULT_RECYCLE_EVERY,
)


def parse_cookies_input(
    cookie_source: Optional[Union[str, Path, List[Dict[str, Any]]]],
    target_hosts: Optional[List[str]] = None,
) -> List[dict]:
    """
    Parse cookies from:
    1. List of dicts (Playwright format or browser export)
    2. Path to JSON file (list of dicts or {"cookies": [...]})
    3. Path to text file ("key=value; key2=value2" or Netscape format)
    4. Raw string ("key=value; key2=value2" or JSON string)

    Replicates each cookie across `target_hosts` using Playwright's `url` parameter
    so IP addresses and all SangTacViet mirrors accept the session cookies.
    """
    if not cookie_source:
        return []

    hosts = target_hosts or [
        "14.225.254.182",
        "sangtacviet.vip",
        "sangtacviet.app",
        "sangtacviet.com",
    ]

    raw_cookies: List[dict] = []

    # If it's already a list of dicts
    if isinstance(cookie_source, list):
        raw_cookies = cookie_source

    elif isinstance(cookie_source, (str, Path)):
        src_path = Path(cookie_source)
        content = ""
        if src_path.exists() and src_path.is_file():
            content = src_path.read_text(encoding="utf-8").strip()
        else:
            content = str(cookie_source).strip()

        if content.startswith("[") or content.startswith("{"):
            try:
                parsed_json = json.loads(content)
                if isinstance(parsed_json, dict) and "cookies" in parsed_json:
                    raw_cookies = parsed_json["cookies"]
                elif isinstance(parsed_json, list):
                    raw_cookies = parsed_json
            except Exception:
                pass

        if not raw_cookies and content:
            # Parse as "name=val; name2=val2"
            for part in content.split(";"):
                part = part.strip()
                if "=" in part:
                    k, v = part.split("=", 1)
                    if k.strip():
                        raw_cookies.append({"name": k.strip(), "value": v.strip()})

    playwright_cookies: List[dict] = []
    seen = set()

    for item in raw_cookies:
        name = item.get("name")
        val = str(item.get("value", ""))
        if not name:
            continue

        for host in hosts:
            proto = "http" if ("14.225.254.182" in host or host.replace(".", "").isdigit()) else "https"
            key = (name, val, host)
            if key not in seen:
                seen.add(key)
                playwright_cookies.append({
                    "name": name,
                    "value": val,
                    "url": f"{proto}://{host}",
                })

    return playwright_cookies


class BrowserManager:
    def __init__(
        self,
        headless: bool = True,
        recycle_every: int = DEFAULT_RECYCLE_EVERY,
        binary_path: Optional[str] = None,
        cookie_source: Optional[Union[str, Path, List[Dict[str, Any]]]] = None,
        target_url: Optional[str] = None,
    ):
        self.headless = headless
        self.recycle_every = recycle_every
        self.binary_path = binary_path or DEFAULT_CHROMIUM_BINARY
        self.target_url = target_url
        
        # Auto-detect cookies file if not provided
        if not cookie_source:
            if Path("cookies.json").exists():
                cookie_source = "cookies.json"
            elif Path("cookies.txt").exists():
                cookie_source = "cookies.txt"

        self.initial_cookies = parse_cookies_input(cookie_source)
        if self.initial_cookies:
            print(f"[+] Đã nạp {len(self.initial_cookies)} cookies xác thực cho session.", flush=True)

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
            default_cookies = [
                {"name": "lang", "value": "vi", "domain": "sangtacviet.app", "path": "/"},
                {"name": "lang", "value": "vi", "domain": "sangtacviet.vip", "path": "/"},
                {"name": "lang", "value": "vi", "domain": "sangtacviet.com", "path": "/"},
                {"name": "lang", "value": "vi", "url": "http://14.225.254.182"},
            ]
            self._context.add_cookies(default_cookies)

            if self.initial_cookies:
                try:
                    self._context.add_cookies(self.initial_cookies)
                except Exception as e:
                    print(f"[!] Cảnh báo nạp cookie: {e}", flush=True)

        self._page = self._context.new_page()
        self._page.set_default_timeout(DEFAULT_PAGE_TIMEOUT_MS)

        # Route Abortion: drop images, fonts, media, and third-party trackers instantly
        self._page.route(BLOCKED_URL_REGEX, lambda route: route.abort())
        self._chapters_since_recycle = 0

    def save_cookies(self, filepath: Union[str, Path] = "cookies.json") -> int:
        """Save current context cookies to a JSON file."""
        if not self._context:
            return 0
        cookies = self._context.cookies()
        path = Path(filepath)
        path.write_text(json.dumps(cookies, ensure_ascii=False, indent=2), encoding="utf-8")
        return len(cookies)

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
