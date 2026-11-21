"""
Configuration constants for the multi-site novel scraper.

Supported sites:
  * SangTacViet (sangtacviet.vip / .app / .com and the direct backend IP)
  * Twkan (twkan.com - Traditional Chinese web novels behind Cloudflare)
"""

from pathlib import Path
import os
import re


def _platform_binary_candidates(version_dir: Path) -> list[Path]:
    """Return the executable paths used by a cached CloakBrowser build."""
    import sys

    if sys.platform == "win32":
        return [version_dir / "chrome.exe"]
    if sys.platform == "darwin":
        return [
            version_dir / "Chromium.app" / "Contents" / "MacOS" / "Chromium",
            version_dir / "chrome",
        ]
    return [version_dir / "chrome"]


def find_cached_cloak_binary() -> str:
    """
    Find the newest cached CloakBrowser binary for the CURRENT platform.

    This is what prevents a Windows build copied from another machine from
    being used on Linux: only a real executable for this OS is returned.
    """
    roots = [Path.home() / ".cloakbrowser"]
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        roots.append(Path(local_appdata) / "cloakbrowser")

    best_path = ""
    best_version: tuple = ()
    for root in roots:
        if not root.is_dir():
            continue
        for version_dir in root.glob("chromium-*"):
            if not version_dir.is_dir():
                continue
            for candidate in _platform_binary_candidates(version_dir):
                if not candidate.is_file() or not os.access(candidate, os.X_OK):
                    continue
                version = tuple(
                    int(p) if p.isdigit() else 0
                    for p in version_dir.name.replace("chromium-", "").split(".")
                )
                if version > best_version:
                    best_version = version
                    best_path = str(candidate)
    return best_path


def get_default_chromium_binary() -> str:
    """
    Resolve the CloakBrowser executable.

    Order:
      1. explicit CLOAKBROWSER_BINARY_PATH (must exist)
      2. newest Linux/macOS/Windows binary already cached in ~/.cloakbrowser
         (works without a license key and avoids the interactive free-key menu)
      3. cloakbrowser's own downloader (requires a free key for the latest build)
    """
    env_path = os.environ.get("CLOAKBROWSER_BINARY_PATH")
    if env_path and Path(env_path).exists():
        return env_path

    cached = find_cached_cloak_binary()
    if cached:
        os.environ["CLOAKBROWSER_BINARY_PATH"] = cached
        return cached

    try:
        from cloakbrowser.download import ensure_binary
        return ensure_binary()
    except Exception:
        pass
    return ""


# Chromium binary path (auto-detect or fallback to user's installed binary)
DEFAULT_CHROMIUM_BINARY = get_default_chromium_binary()

# Base domains
DEFAULT_BASE_URL = "https://sangtacviet.vip"
DEFAULT_COOKIES_FILE = Path("cookies.json")
TWKAN_COOKIES_FILE = Path("cookies_twkan.json")

# Domains that the SangTacViet adapter knows how to talk to.
ALLOWED_DOMAINS = [
    "14.225.254.182",
    "sangtacviet.vip",
    "sangtacviet.com",
    "sangtacviet.app",
    "sangtacvietcdn.xyz",
]

# Twkan can serve the same book from a few mirror hostnames.
TWKAN_DOMAINS = [
    "twkan.com",
    "www.twkan.com",
    "twkan.cc",
    "twkan.net",
]

# Route Abortion: Block heavy non-essential resources to load pages under 500ms.
# NOTE: Cloudflare challenge assets must never match this pattern.
BLOCKED_RESOURCE_TYPES = {"image", "media", "font", "texttrack", "eventsource", "websocket"}
BLOCKED_URL_REGEX = re.compile(
    r"(\.png|\.jpg|\.jpeg|\.gif|\.webp|\.woff|\.woff2|\.ttf|\.mp3|\.mp4|\.ico|\.svg"
    r"|google-analytics|googletagmanager|doubleclick|adservice|connect\.facebook"
    r"|pubadx|adsbygoogle|popads|propellerads|onclickads|adsterra)",
    re.IGNORECASE,
)

# Scraping settings (SangTacViet: keep a slow pace to avoid anti-spam code 21)
DEFAULT_DELAY_MIN = 10.0
DEFAULT_DELAY_MAX = 10.0
DEFAULT_PAGE_TIMEOUT_MS = 30000
DEFAULT_CONTENT_WAIT_TIMEOUT_SEC = 12
DEFAULT_RECYCLE_EVERY = 50

# Twkan is far more sensitive to bursts: Cloudflare throws a managed challenge
# after a handful of rapid navigations. Keep a human-ish cadence.
TWKAN_DELAY_MIN = 3.5
TWKAN_DELAY_MAX = 5.5
TWKAN_BURST_SIZE = 12
TWKAN_BURST_SLEEP = 15.0
TWKAN_CHALLENGE_TIMEOUT_SEC = 35.0
TWKAN_CHALLENGE_COOLDOWN_SEC = 20.0

# Output directory
DEFAULT_OUTPUT_DIR = Path("output")
