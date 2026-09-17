"""
Core scraper engine for SangTacViet with automatic chapter navigation,
checkpointing, rate-limiting, and error recovery.
"""

import random
import re
import time
from pathlib import Path
from typing import Callable, Optional, Tuple
from urllib.parse import urlparse

from browser_manager import BrowserManager
from checkpoint_manager import CheckpointManager
from config import (
    DEFAULT_BASE_URL,
    DEFAULT_CONTENT_WAIT_TIMEOUT_SEC,
    DEFAULT_DELAY_MAX,
    DEFAULT_DELAY_MIN,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_PAGE_TIMEOUT_MS,
    DEFAULT_RECYCLE_EVERY,
)
from extractor import extract_chapter_payload
from models import ChapterRecord
from storage import JsonlStorage


class SangTacVietScraper:
    def __init__(
        self,
        target_url: str,
        max_chapters: Optional[int] = None,
        headless: bool = True,
        output_dir: Path = DEFAULT_OUTPUT_DIR,
        recycle_every: int = DEFAULT_RECYCLE_EVERY,
        on_chapter_crawled: Optional[Callable[[ChapterRecord, int], None]] = None,
    ):
        self.target_url = target_url.strip()
        self.max_chapters = max_chapters
        self.headless = headless
        self.output_dir = Path(output_dir)
        self.recycle_every = recycle_every
        self.on_chapter_crawled = on_chapter_crawled

        self.source, self.story_id, self.initial_chapter_id = self._parse_url(self.target_url)

        self.storage = JsonlStorage(self.story_id, self.output_dir)
        self.checkpoint = CheckpointManager(self.story_id, self.output_dir)
        self.browser_manager = BrowserManager(
            headless=self.headless,
            recycle_every=self.recycle_every,
        )

    def _parse_url(self, url: str) -> Tuple[str, str, Optional[str]]:
        """
        Parses SangTacViet URL structure:
        - Story:   https://sangtacviet.app/truyen/{source}/1/{story_id}/
        - Chapter: https://sangtacviet.app/truyen/{source}/1/{story_id}/{chapter_id}/
        """
        parsed = urlparse(url)
        path = parsed.path.strip("/")
        parts = path.split("/")

        if len(parts) >= 4 and parts[0] == "truyen":
            source = parts[1]
            story_id = parts[3]
            chapter_id = parts[4] if len(parts) >= 5 and parts[4] and parts[4] != "0" else None
            return source, story_id, chapter_id

        raise ValueError(
            f"URL không đúng định dạng SangTacViet: {url}\n"
            f"Mẫu hợp lệ: https://sangtacviet.app/truyen/dich/1/53028/ hoặc kèm chapter id"
        )

    def _resolve_first_chapter(self, page) -> str:
        """Find the first available chapter ID from the story page."""
        story_url = f"{DEFAULT_BASE_URL}/truyen/{self.source}/1/{self.story_id}/"
        page.goto(story_url, timeout=DEFAULT_PAGE_TIMEOUT_MS)
        time.sleep(1.5)

        # 1. Check if an <a> with id or onclick has chapter ID
        first_id = page.evaluate("""() => {
            const el = document.querySelector(".listchapitem, a[id]");
            if (el && el.id && /^\\d+$/.test(el.id)) return el.id;
            if (el && el.getAttribute("onclick")) {
                const m = el.getAttribute("onclick").match(/\\d+/);
                if (m) return m[0];
            }
            return null;
        }""")

        if first_id:
            return str(first_id)

        # 2. Try clicking the first chapter item to see where it navigates
        try:
            with page.expect_navigation(timeout=6000):
                page.locator(".listchapitem").first.click(timeout=3000)
            _, _, clicked_id = self._parse_url(page.url)
            if clicked_id:
                return clicked_id
        except Exception:
            pass

        # 3. Default fallback: SangTacViet numbering usually starts at 1
        return "1"

    def run(self) -> int:
        """Execute scraping loop with checkpointing and error handling."""
        page = self.browser_manager.start()
        crawled_count = 0

        try:
            # Determine starting chapter
            current_chapter_id = self.initial_chapter_id

            # Check if resuming from checkpoint
            if self.checkpoint.next_chapter_id and (not self.initial_chapter_id or self.checkpoint.is_completed(self.initial_chapter_id)):
                current_chapter_id = self.checkpoint.next_chapter_id
            elif self.checkpoint.last_chapter_id and (not self.initial_chapter_id or self.checkpoint.is_completed(self.initial_chapter_id)):
                current_chapter_id = self.checkpoint.last_chapter_id

            if not current_chapter_id:
                current_chapter_id = self._resolve_first_chapter(page)

            while current_chapter_id:
                if self.max_chapters is not None and crawled_count >= self.max_chapters:
                    break

                chapter_url = (
                    f"{DEFAULT_BASE_URL}/truyen/{self.source}/1/{self.story_id}/{current_chapter_id}/"
                )

                # Skip if already in checkpoint (unless running single-chapter smoke test)
                if self.checkpoint.is_completed(current_chapter_id) and (self.max_chapters != 1):
                    # Check if next_chapter_id is known
                    if self.checkpoint.next_chapter_id and self.checkpoint.next_chapter_id != current_chapter_id:
                        current_chapter_id = self.checkpoint.next_chapter_id
                        continue
                    else:
                        next_id = self._peek_next_chapter(page, chapter_url)
                        if not next_id or next_id == current_chapter_id:
                            break
                        current_chapter_id = next_id
                        continue

                # Scrape current chapter
                record, next_chapter_id = self._scrape_single_chapter(
                    page, current_chapter_id, chapter_url
                )

                if record:
                    self.storage.append_chapter(record)
                    self.checkpoint.mark_completed(
                        current_chapter_id, record.story_title, next_chapter_id or ""
                    )
                    crawled_count += 1

                    if self.on_chapter_crawled:
                        self.on_chapter_crawled(record, crawled_count)

                # Advance to next chapter
                if not next_chapter_id or next_chapter_id == "0" or next_chapter_id == current_chapter_id:
                    break

                current_chapter_id = next_chapter_id

                # Friendly rate-limiting delay
                delay = random.uniform(DEFAULT_DELAY_MIN, DEFAULT_DELAY_MAX)
                time.sleep(delay)

                # Check if context recycle is needed to free memory
                page = self.browser_manager.step_chapter()

        finally:
            self.browser_manager.close()

        return crawled_count

    def _scrape_single_chapter(
        self, page, chapter_id: str, chapter_url: str
    ) -> Tuple[Optional[ChapterRecord], Optional[str]]:
        """Load chapter page, trigger decryption click, and extract content."""
        page.goto(chapter_url, timeout=DEFAULT_PAGE_TIMEOUT_MS)
        time.sleep(0.8)

        # Trigger STV AJAX reading mechanism
        try:
            page.click("#maincontent", timeout=2500)
        except Exception:
            pass

        # Wait for content tokens to populate (handling any intermediate page reload)
        start_wait = time.time()
        loaded = False

        while time.time() - start_wait < DEFAULT_CONTENT_WAIT_TIMEOUT_SEC:
            time.sleep(0.4)
            try:
                cnt = page.evaluate("document.querySelectorAll('i[t]').length")
                if cnt > 0:
                    loaded = True
                    break
            except Exception:
                continue

        if not loaded:
            return None, None

        # Extract structured content
        try:
            return extract_chapter_payload(page, self.story_id, chapter_id, chapter_url)
        except Exception:
            return None, None

    def _peek_next_chapter(self, page, chapter_url: str) -> Optional[str]:
        """Inspect next chapter link from a previously crawled page."""
        page.goto(chapter_url, timeout=DEFAULT_PAGE_TIMEOUT_MS)
        time.sleep(1)
        try:
            next_href = page.evaluate("""() => {
                const nextBtn = document.querySelector("#navnexttop") || document.querySelector("#navnextbot");
                return nextBtn ? nextBtn.getAttribute("href") : null;
            }""")
            if next_href:
                candidate = next_href.strip().rstrip("/").split("/")[-1]
                if candidate and candidate != "0":
                    return candidate
        except Exception:
            pass
        return None
