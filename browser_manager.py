"""
Browser Manager: Handles CloakBrowser lifecycle, route abortion, and memory recycling.
"""

import json
import os
import sys
import time
if sys.platform == 'win32':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8')
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from config import (
    BLOCKED_URL_REGEX,
    DEFAULT_CHROMIUM_BINARY,
    DEFAULT_PAGE_TIMEOUT_MS,
    DEFAULT_RECYCLE_EVERY,
)

# Cloudflare / WAF interstitial markers
CHALLENGE_TITLE_MARKERS = (
    "just a moment",
    "attention required",
    "checking your browser",
    "verify you are human",
    "ddos protection",
    "please wait",
)
CHALLENGE_DOM_SELECTORS = (
    "#challenge-form",
    "#challenge-stage",
    "#cf-challenge-running",
    ".cf-browser-verification",
)


def page_is_challenge(page: Any) -> bool:
    """Return True while the tab is showing a Cloudflare/WAF challenge page."""
    try:
        title = (page.title() or "").lower()
        url = page.url or ""
    except Exception:
        # A navigation in flight makes the JS context temporarily unavailable.
        return True

    if any(marker in title for marker in CHALLENGE_TITLE_MARKERS):
        return True
    if "/cdn-cgi/challenge-platform" in url or "__cf_chl_" in url:
        return True
    try:
        return bool(
            page.evaluate(
                """(selectors) => selectors.some(s => {
                    const el = document.querySelector(s);
                    return !!el && (el.offsetParent !== null || s.includes('iframe'));
                })""",
                list(CHALLENGE_DOM_SELECTORS),
            )
        )
    except Exception:
        return False


def _try_click_turnstile(page: Any) -> None:
    """Best-effort click on a Turnstile checkbox (managed challenges are often
    already auto-solved by CloakBrowser; this is only a nudge)."""
    selectors = (
        "input[type=checkbox]",
        ".ctp-checkbox-label",
        "#challenge-stage",
    )
    try:
        frames = list(page.frames)
    except Exception:
        frames = []
    for frame in frames:
        try:
            if not any(k in (frame.url or "") for k in ("cloudflare", "turnstile", "challenge")):
                continue
            for sel in selectors:
                try:
                    frame.click(sel, timeout=400)
                    return
                except Exception:
                    continue
        except Exception:
            continue
    for sel in selectors:
        try:
            page.click(sel, timeout=400)
            return
        except Exception:
            continue


def wait_through_challenge(
    page: Any,
    timeout: float = 35.0,
    click: bool = True,
    verbose: bool = True,
) -> bool:
    """
    Wait for an automatic Cloudflare challenge to resolve.

    Returns True when the page no longer looks like a challenge.
    """
    start = time.time()
    last_click = 0.0
    notified = False
    while time.time() - start < timeout:
        if not page_is_challenge(page):
            return True
        if verbose and not notified:
            print("    [CF] Đang chờ Cloudflare giải challenge tự động...", flush=True)
            notified = True
        if click and time.time() - last_click >= 4.0:
            try:
                _try_click_turnstile(page)
            except Exception:
                pass
            last_click = time.time()
        time.sleep(0.75)
    return not page_is_challenge(page)


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
    so IP addresses and all mirror domains accept the session cookies.
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
        cookie_hosts: Optional[List[str]] = None,
        humanize: bool = True,
        challenge_timeout: float = 35.0,
    ):
        self.headless = headless
        self.recycle_every = recycle_every
        self.binary_path = binary_path or DEFAULT_CHROMIUM_BINARY
        self.target_url = target_url
        self.cookie_hosts = cookie_hosts
        self.humanize = humanize
        self.challenge_timeout = challenge_timeout

        # Auto-detect cookies file if not provided
        if not cookie_source:
            if Path("cookies.json").exists():
                cookie_source = "cookies.json"
            elif Path("cookies.txt").exists():
                cookie_source = "cookies.txt"

        self.initial_cookies = parse_cookies_input(cookie_source, target_hosts=cookie_hosts)
        if self.initial_cookies:
            print(f"[+] Đã nạp {len(self.initial_cookies)} cookies xác thực cho session.", flush=True)

        # Ensure CloakBrowser env var is set if valid
        if self.binary_path:
            os.environ["CLOAKBROWSER_BINARY_PATH"] = self.binary_path

        self._browser: Optional[Any] = None
        self._context: Optional[Any] = None
        self._page: Optional[Any] = None
        self._saved_cookies: List[dict] = []
        self._chapters_since_recycle = 0

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def start(self) -> Any:
        """Start CloakBrowser and create the first context."""
        if self._browser and self._page:
            return self._page

        try:
            from cloakbrowser import launch
        except ImportError as exc:
            raise RuntimeError(
                "Thiếu gói cloakbrowser. Cài lại bằng:\n"
                "  pip install -U cloakbrowser\n"
                "Scraper này chỉ dùng Chromium stealth của CloakBrowser, "
                "không dùng Chromium tải qua Playwright."
            ) from exc

        launch_kwargs = dict(
            headless=self.headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )
        if self.binary_path:
            # Guarantees CloakBrowser uses its own Linux/macOS/Windows build
            # instead of a binary copied from another OS.
            os.environ["CLOAKBROWSER_BINARY_PATH"] = self.binary_path
        if self.humanize:
            launch_kwargs["humanize"] = True

        try:
            self._browser = launch(**launch_kwargs)
        except Exception as e:
            err_msg = str(e)
            if "session limit reached" in err_msg.lower() or "license" in err_msg.lower():
                print("\n[!] LỖI PHIÊN CLOAKBROWSER: Giới hạn 1 session đồng thời của gói Free.", flush=True)
                print("[!] Tiến trình trước đó vừa bị dừng đột ngột khiến server CloakBrowser chưa kịp nhả session.", flush=True)
                print("[!] Vui lòng đợi khoảng 3-4 phút để server tự động reset slot rồi chạy lại.\n", flush=True)
            raise

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
            ignore_https_errors=True,
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

        # Route Abortion: drop images, fonts, media, and third-party trackers instantly,
        # but NEVER abort Cloudflare Turnstile verification assets
        def _filter_route(route):
            url = route.request.url.lower()
            if "cloudflare" in url or "turnstile" in url or "challenge" in url:
                route.continue_()
            else:
                route.abort()

        self._page.route(BLOCKED_URL_REGEX, _filter_route)
        self._chapters_since_recycle = 0

    def save_cookies(self, filepath: Union[str, Path] = "cookies.json") -> int:
        """Save current context cookies to a JSON file."""
        if not self._context:
            return 0
        cookies = self._context.cookies()
        path = Path(filepath)
        path.write_text(json.dumps(cookies, ensure_ascii=False, indent=2), encoding="utf-8")
        return len(cookies)

    def step_chapter(self) -> Any:
        """
        Notify that a chapter has been processed.
        Recycles context every `recycle_every` chapters to prevent RAM leaks.
        """
        self._chapters_since_recycle += 1
        if self._chapters_since_recycle >= self.recycle_every:
            self._create_fresh_context()
        return self._page

    def recycle_now(self) -> Any:
        """Force a fresh BrowserContext (keeps cookies) right away."""
        self._create_fresh_context()
        return self._page

    @property
    def page(self) -> Any:
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
