"""
Core scraper engine for SangTacViet with automatic chapter navigation,
checkpointing, rate-limiting, and error recovery.
"""

import random
import re
import time
from pathlib import Path
from typing import Any, Callable, List, Optional, Tuple
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
        start_index: int = 1,
        reset: bool = False,
        headless: bool = True,
        output_dir: Path = DEFAULT_OUTPUT_DIR,
        recycle_every: int = DEFAULT_RECYCLE_EVERY,
        cookie_source: Optional[Any] = None,
        on_chapter_crawled: Optional[Callable[[ChapterRecord, int, int], None]] = None,
    ):
        self.target_url = target_url.strip()
        self.max_chapters = max_chapters
        self.start_index = max(1, start_index)
        self.reset = reset
        self.headless = headless
        self.output_dir = Path(output_dir)
        self.recycle_every = recycle_every
        self.on_chapter_crawled = on_chapter_crawled

        self.base_url, self.source, self.story_id, self.initial_chapter_id = self._parse_url(self.target_url)

        self.storage = JsonlStorage(self.story_id, self.output_dir)
        self.checkpoint = CheckpointManager(self.story_id, self.output_dir)
        self.browser_manager = BrowserManager(
            headless=self.headless,
            recycle_every=self.recycle_every,
            cookie_source=cookie_source,
            target_url=self.base_url,
        )

    def _parse_url(self, url: str) -> Tuple[str, str, str, Optional[str]]:
        """
        Parses SangTacViet URL structure:
        - Story:   http://14.225.254.182/truyen/{source}/1/{story_id}/
        - Chapter: https://sangtacviet.app/truyen/{source}/1/{story_id}/{chapter_id}/
        """
        parsed = urlparse(url)
        path = parsed.path.strip("/")
        parts = path.split("/")

        base_url = f"{parsed.scheme}://{parsed.netloc}" if parsed.netloc else DEFAULT_BASE_URL

        if len(parts) >= 4 and parts[0] == "truyen":
            source = parts[1]
            story_id = parts[3]
            chapter_id = parts[4] if len(parts) >= 5 and parts[4] and parts[4] != "0" else None
            return base_url, source, story_id, chapter_id

        raise ValueError(
            f"URL không đúng định dạng SangTacViet: {url}\n"
            f"Mẫu hợp lệ: https://sangtacviet.app/truyen/dich/1/53028/ hoặc kèm chapter id"
        )

    def _fetch_chapter_list(self, page) -> List[Tuple[str, str]]:
        """Fetch full ordered chapter list (chapter_id, chapter_title) from API."""
        story_url = f"{self.base_url}/truyen/{self.source}/1/{self.story_id}/"
        try:
            page.goto(story_url, wait_until="domcontentloaded", timeout=DEFAULT_PAGE_TIMEOUT_MS)
            time.sleep(1.0)
            api_url = f"/index.php?ngmar=chapterlist&h={self.source}&bookid={self.story_id}&sajax=getchapterlist"
            data = page.evaluate(f"""async () => {{
                try {{
                    const r = await fetch('{api_url}');
                    const j = await r.json();
                    if (j && j.data) return j.data;
                }} catch (e) {{}}
                return null;
            }}""")
            if not data:
                return []
            chapters = []
            for item in data.split("-//-"):
                parts = item.split("-/-")
                if len(parts) >= 3:
                    cid = parts[1].strip()
                    title = parts[2].strip()
                    chapters.append((cid, title))
                elif len(parts) >= 2:
                    cid = parts[1].strip()
                    chapters.append((cid, ""))
            return chapters
        except Exception:
            return []

    def _resolve_first_chapter(self, page) -> str:
        """Find the first available chapter ID from the story page or chapterlist API."""
        chapters = self._fetch_chapter_list(page)
        if chapters:
            return chapters[0][0]

        story_url = f"{self.base_url}/truyen/{self.source}/1/{self.story_id}/"
        page.goto(story_url, wait_until="domcontentloaded", timeout=DEFAULT_PAGE_TIMEOUT_MS)
        time.sleep(1.0)

        # Check if an <a> with id or onclick has chapter ID
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

        # Default fallback: SangTacViet numbering starts at 1
        return "1"

    def run(self) -> int:
        """Execute scraping loop with checkpointing, retry, and memory recycling."""
        page = self.browser_manager.start()
        crawled_count = 0

        if self.reset:
            self.storage.reset()
            self.checkpoint.reset()

        try:
            # Fetch ordered chapter list from SangTacViet
            chapter_entries = self._fetch_chapter_list(page)

            if chapter_entries:
                chapter_ids = [c[0] for c in chapter_entries]
                chapter_titles = {c[0]: c[1] for c in chapter_entries}

                start_idx = self.start_index - 1
                if self.initial_chapter_id and self.initial_chapter_id in chapter_ids and self.start_index == 1:
                    start_idx = chapter_ids.index(self.initial_chapter_id)

                start_idx = max(0, min(start_idx, len(chapter_entries) - 1))
                end_idx = (start_idx + self.max_chapters) if self.max_chapters else len(chapter_entries)
                target_entries = chapter_entries[start_idx:end_idx]
                total_in_batch = len(target_entries)

                for idx, (cid, api_title) in enumerate(target_entries):
                    current_num = start_idx + idx + 1

                    # Skip if already in checkpoint (unless single-chapter smoke test)
                    if self.checkpoint.is_completed(cid) and (self.max_chapters != 1):
                        continue

                    chapter_url = f"{self.base_url}/truyen/{self.source}/1/{self.story_id}/{cid}/"

                    # Scrape chapter with retry
                    record = None
                    for attempt in range(2):
                        record, _ = self._scrape_single_chapter(page, cid, chapter_url, need_next_id=False)
                        if record:
                            break
                        time.sleep(1.0)

                    if record:
                        if api_title and (not record.chapter_title or record.chapter_title in ("_", record.story_title)):
                            record.chapter_title = api_title
                        
                        self.storage.append_chapter(record)
                        next_cid = target_entries[idx + 1][0] if (idx + 1 < total_in_batch) else ""
                        self.checkpoint.mark_completed(cid, record.story_title, next_cid)
                        crawled_count += 1

                        if self.on_chapter_crawled:
                            try:
                                self.on_chapter_crawled(record, current_num, total_in_batch)
                            except TypeError:
                                self.on_chapter_crawled(record, current_num)
                    else:
                        print(f"\n[Cảnh báo] Bỏ qua chương {cid} ({api_title}) do không tải được nội dung.", flush=True)

                    delay = random.uniform(DEFAULT_DELAY_MIN, DEFAULT_DELAY_MAX)
                    time.sleep(delay)
                    page = self.browser_manager.step_chapter()

            else:
                # Fallback to navigation-based scraping if chapterlist API returns empty
                current_chapter_id = self.initial_chapter_id
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
                        f"{self.base_url}/truyen/{self.source}/1/{self.story_id}/{current_chapter_id}/"
                    )

                    if self.checkpoint.is_completed(current_chapter_id) and (self.max_chapters != 1):
                        if self.checkpoint.next_chapter_id and self.checkpoint.next_chapter_id != current_chapter_id:
                            current_chapter_id = self.checkpoint.next_chapter_id
                            continue
                        else:
                            break

                    record, next_chapter_id = self._scrape_single_chapter(page, current_chapter_id, chapter_url, need_next_id=True)
                    if record:
                        self.storage.append_chapter(record)
                        self.checkpoint.mark_completed(current_chapter_id, record.story_title, next_chapter_id or "")
                        crawled_count += 1
                        if self.on_chapter_crawled:
                            self.on_chapter_crawled(record, crawled_count)

                    if not next_chapter_id or next_chapter_id == "0" or next_chapter_id == current_chapter_id:
                        break
                    current_chapter_id = next_chapter_id
                    delay = random.uniform(DEFAULT_DELAY_MIN, DEFAULT_DELAY_MAX)
                    time.sleep(delay)
                    page = self.browser_manager.step_chapter()

        finally:
            self.browser_manager.close()

        return crawled_count

    def _scrape_single_chapter(
        self, page, chapter_id: str, chapter_url: str, need_next_id: bool = True
    ) -> Tuple[Optional[ChapterRecord], Optional[str]]:
        """Load chapter page, trigger decryption click, and extract content."""
        try:
            page.goto(chapter_url, wait_until="domcontentloaded", timeout=DEFAULT_PAGE_TIMEOUT_MS)
        except Exception:
            return None, None
        time.sleep(0.3)

        # Trigger STV AJAX reading mechanism
        try:
            page.click("#maincontent", timeout=2000)
        except Exception:
            pass

        # Wait for content tokens to populate (handling any intermediate page reload)
        start_wait = time.time()
        loaded = False

        while time.time() - start_wait < DEFAULT_CONTENT_WAIT_TIMEOUT_SEC:
            time.sleep(0.2)
            try:
                cnt = page.evaluate("() => document.querySelectorAll('i[t]').length")
                if cnt and cnt > 50:
                    loaded = True
                    break
                # If 2.0s elapsed and still not loaded, re-click #maincontent
                if time.time() - start_wait > 2.0:
                    try:
                        page.click("#maincontent", timeout=800)
                    except Exception:
                        pass
            except Exception:
                continue

        if not loaded:
            return None, None

        # Only wait for next chapter link if not already known
        if need_next_id:
            start_nav = time.time()
            while time.time() - start_nav < 2.5:
                try:
                    has_next = page.evaluate("""() => {
                        const btn = document.querySelector("#navnexttop") || document.querySelector("#navnextbot");
                        if (!btn) return false;
                        const h = btn.getAttribute("href") || "";
                        return h && !h.endsWith("/0/") && h.includes("/truyen/");
                    }""")
                    if has_next:
                        break
                except Exception:
                    pass
                time.sleep(0.2)

        # Extract structured content (Vietnamese only for maximum speed)
        try:
            record, next_chapter_id = extract_chapter_payload(
                page, self.story_id, chapter_id, chapter_url, extract_bilingual=False
            )
            # Sequential chapter fallback if DOM next link is 0 or empty and chapter_id is small integer
            if record and (not next_chapter_id or next_chapter_id == "0") and chapter_id.isdigit() and len(chapter_id) <= 6:
                next_chapter_id = str(int(chapter_id) + 1)
            return record, next_chapter_id
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
        # Fallback to next sequential chapter ID
        clean = chapter_url.strip().rstrip("/")
        parts = clean.split("/")
        if parts and parts[-1].isdigit():
            return str(int(parts[-1]) + 1)
        return None

