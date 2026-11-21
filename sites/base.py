"""
Contract shared by every supported novel site.

Each adapter knows how to:
  * recognise its own URLs and extract (story id, chapter id)
  * fetch the ordered chapter list
  * open a chapter and wait until its content is ready
  * extract a ``ChapterRecord`` from the rendered page

The orchestration (checkpoint, retry, pacing, storage) lives in ``scraper.py``
and is site-agnostic.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
import json
from pathlib import Path
from typing import List, Optional, Tuple

from browser_manager import page_is_challenge, wait_through_challenge
from config import (
    DEFAULT_CONTENT_WAIT_TIMEOUT_SEC,
    DEFAULT_PAGE_TIMEOUT_MS,
)
from models import ChapterRecord


# Open-status values returned by SiteAdapter.open_chapter()
OPEN_OK = "ok"
OPEN_CHALLENGE = "challenge"
OPEN_NO_CONTENT = "no-content"
OPEN_ERROR = "error"


@dataclass
class StoryRef:
    """Normalised identity of a story on a given site."""
    site: str
    base_url: str
    story_id: str
    source: str = ""
    initial_chapter_id: Optional[str] = None


@dataclass
class ChapterEntry:
    """One row of a chapter list."""
    chapter_id: str
    title: str = ""
    url: str = ""
    order: int = 0


class SiteAdapter(ABC):
    """Base class for site-specific scraping behaviour."""

    name: str = "base"
    display_name: str = "Base"
    cookie_hosts: Tuple[str, ...] = ()
    default_cookie_file: Optional[str] = None

    # Pacing (seconds between chapters)
    delay_min: float = 2.0
    delay_max: float = 4.0
    burst_size: int = 0
    burst_sleep: float = 0.0
    challenge_timeout: float = 35.0
    challenge_cooldown: float = 20.0

    # Extraction options
    extract_bilingual: bool = False

    # Some sites handle their own captcha inside wait_content_ready (SangTacViet).
    detect_challenge: bool = True

    # ------------------------------------------------------------------ URL
    @classmethod
    @abstractmethod
    def matches(cls, url: str) -> bool:
        """Return True when this adapter can handle ``url``."""

    @abstractmethod
    def parse(self, url: str) -> StoryRef:
        """Normalise ``url`` into a StoryRef."""

    # --------------------------------------------------------------- chapters
    @abstractmethod
    def fetch_chapter_list(self, page, ref: StoryRef) -> List[ChapterEntry]:
        """Return the full ordered chapter list (may be empty on failure)."""

    def chapter_url(self, ref: StoryRef, chapter_id: str) -> str:
        """Build the canonical chapter URL."""
        raise NotImplementedError

    def resolve_first_chapter(self, page, ref: StoryRef) -> Optional[str]:
        """Fallback: find the first chapter id when the list is unavailable."""
        entries = self.fetch_chapter_list(page, ref)
        return entries[0].chapter_id if entries else None

    # ------------------------------------------------------------------ open
    def open_chapter(self, page, entry: ChapterEntry, ref: StoryRef) -> str:
        """
        Navigate to a chapter and wait for its body to render.

        Returns one of OPEN_OK / OPEN_CHALLENGE / OPEN_NO_CONTENT / OPEN_ERROR.
        """
        url = entry.url or self.chapter_url(ref, entry.chapter_id)
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=DEFAULT_PAGE_TIMEOUT_MS)
        except Exception:
            return OPEN_ERROR

        challenge_seen = self.detect_challenge and page_is_challenge(page)
        if challenge_seen:
            if not wait_through_challenge(page, timeout=self.challenge_timeout):
                # One reload often completes the challenge once cf_clearance is set.
                try:
                    page.reload(wait_until="domcontentloaded", timeout=DEFAULT_PAGE_TIMEOUT_MS)
                except Exception:
                    return OPEN_ERROR
                if not wait_through_challenge(page, timeout=self.challenge_timeout):
                    return OPEN_CHALLENGE
            self._persist_cookies(page)

        if self.wait_content_ready(page):
            return OPEN_OK
        return OPEN_NO_CONTENT

    def _persist_cookies(self, page) -> None:
        """Save Cloudflare/session cookies so the next run starts warm."""
        if not self.default_cookie_file:
            return
        try:
            cookies = page.context.cookies()
            Path(self.default_cookie_file).write_text(
                json.dumps(cookies, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass

    def wait_content_ready(self, page, timeout: float = DEFAULT_CONTENT_WAIT_TIMEOUT_SEC) -> bool:
        """Wait until the chapter body is present and non-trivial."""
        raise NotImplementedError

    # -------------------------------------------------------------- extract
    @abstractmethod
    def extract(
        self, page, ref: StoryRef, entry: ChapterEntry
    ) -> Tuple[Optional[ChapterRecord], Optional[str]]:
        """Return (record, next_chapter_id) for the currently open chapter."""
