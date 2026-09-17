"""
Configuration constants for SangTacViet CloakBrowser Scraper.
"""

from pathlib import Path
import os
import re

# Chromium binary path (auto-detect or fallback to user's installed binary)
DEFAULT_CHROMIUM_BINARY = os.environ.get(
    "CLOAKBROWSER_BINARY_PATH",
    "/Users/binhan/.cloakbrowser/chromium-145.0.7632.109.2/Chromium.app/Contents/MacOS/Chromium"
)

# Base domains
DEFAULT_BASE_URL = "https://sangtacviet.app"
ALLOWED_DOMAINS = [
    "sangtacviet.app",
    "sangtacviet.com",
    "sangtacviet.vip",
    "sangtacvietcdn.xyz",
]

# Route Abortion: Block heavy non-essential resources to load pages under 500ms
BLOCKED_RESOURCE_TYPES = {"image", "media", "font", "texttrack", "eventsource", "websocket"}
BLOCKED_URL_REGEX = re.compile(
    r"(\.png|\.jpg|\.jpeg|\.gif|\.webp|\.woff|\.woff2|\.ttf|\.mp3|\.mp4|\.ico|\.svg"
    r"|google-analytics|googletagmanager|doubleclick|adservice|connect\.facebook)",
    re.IGNORECASE,
)

# Scraping settings
DEFAULT_DELAY_MIN = 0.8
DEFAULT_DELAY_MAX = 1.5
DEFAULT_PAGE_TIMEOUT_MS = 30000
DEFAULT_CONTENT_WAIT_TIMEOUT_SEC = 12
DEFAULT_RECYCLE_EVERY = 50

# Output directory
DEFAULT_OUTPUT_DIR = Path("output")
