"""
Core scraper engine.

Site-specific behaviour lives in ``sites/``; this module owns the generic
pipeline: chapter navigation, checkpointing, retry/backoff, pacing, browser
recycling and storage.

Supported sources:
  * SangTacViet (Vietnamese / convert, VIP aware)
  * Twkan (Traditional Chinese, Cloudflare protected)
"""

import random
import time
from pathlib import Path
from typing import Any, Callable, List, Optional, Tuple
from urllib.parse import urlparse

from browser_manager import BrowserManager
from checkpoint_manager import CheckpointManager
from config import (
    DEFAULT_OUTPUT_DIR,
    DEFAULT_RECYCLE_EVERY,
)
from models import ChapterRecord
from sites import (
    ChapterEntry,
    OPEN_CHALLENGE,
    OPEN_NO_CONTENT,
    OPEN_OK,
    resolve_site,
)
from storage import JsonlStorage


class NovelScraper:
    """Generic multi-site novel scraper."""

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
        delay: Optional[float] = None,
        humanize: bool = True,
    ):
        self.target_url = target_url.strip()
        self.max_chapters = max_chapters
        self.start_index = max(1, start_index)
        self.reset = reset
        self.headless = headless
        self.output_dir = Path(output_dir)
        self.recycle_every = recycle_every
        self.on_chapter_crawled = on_chapter_crawled
        self.delay = delay
        self.humanize = humanize

        self.adapter, self.ref = resolve_site(self.target_url)

        # Backwards-compatible attributes used by tests / callers.
        self.base_url = self.ref.base_url
        self.source = self.ref.source
        self.story_id = self.ref.story_id
        self.initial_chapter_id = self.ref.initial_chapter_id

        self.storage = JsonlStorage(self.story_id, self.output_dir)
        self.checkpoint = CheckpointManager(self.story_id, self.output_dir)

        cookie_hosts = list(self.adapter.cookie_hosts) or [urlparse(self.base_url).netloc]
        if cookie_source is None:
            cookie_source = self.adapter.default_cookie_file

        self.browser_manager = BrowserManager(
            headless=self.headless,
            recycle_every=self.recycle_every,
            cookie_source=cookie_source,
            target_url=self.base_url,
            cookie_hosts=cookie_hosts,
            humanize=self.humanize,
            challenge_timeout=self.adapter.challenge_timeout,
        )

        self._page = None

    # ------------------------------------------------------------------ run
    def run(self) -> int:
        """Execute the scraping loop with checkpointing, retry, and recycling."""
        self._page = self.browser_manager.start()

        if self.reset:
            self.storage.reset()
            self.checkpoint.reset()

        crawled = 0
        try:
            print(
                f"[+] Nguồn: {self.adapter.display_name} | Truyện ID: {self.story_id}",
                flush=True,
            )
            chapter_entries = self.adapter.fetch_chapter_list(self._page, self.ref)

            if chapter_entries:
                print(f"[+] Đã lấy danh sách {len(chapter_entries)} chương.", flush=True)
                crawled = self._run_from_list(chapter_entries)
            else:
                print(
                    "[!] Không lấy được danh sách chương, chuyển sang chế độ điều hướng tuần tự.",
                    flush=True,
                )
                crawled = self._run_by_navigation()
                if crawled == 0:
                    print(
                        "[!] Không cào được chương nào. Nếu đây là Twkan và vừa gặp Cloudflare, "
                        "hãy thử chạy lại với --headed (hoặc đợi vài phút rồi tiếp tục) — "
                        "checkpoint sẽ giữ nguyên tiến độ.",
                        flush=True,
                    )

        finally:
            self.browser_manager.close()

        return crawled

    # ------------------------------------------------------------ list mode
    def _run_from_list(self, chapter_entries: List[ChapterEntry]) -> int:
        chapter_ids = [c.chapter_id for c in chapter_entries]

        start_idx = self.start_index - 1
        if (
            self.initial_chapter_id
            and self.initial_chapter_id in chapter_ids
            and self.start_index == 1
        ):
            start_idx = chapter_ids.index(self.initial_chapter_id)

        start_idx = max(0, min(start_idx, len(chapter_entries) - 1))
        end_idx = (start_idx + self.max_chapters) if self.max_chapters else len(chapter_entries)
        target_entries = chapter_entries[start_idx:end_idx]
        total_in_batch = len(target_entries)

        crawled = 0
        for idx, entry in enumerate(target_entries):
            current_num = start_idx + idx + 1

            # Skip already-checkpointed chapters (unless a 1-chapter smoke test).
            if self.checkpoint.is_completed(entry.chapter_id) and (self.max_chapters != 1):
                continue

            record, _ = self._scrape_entry(entry)
            if record:
                if not record.chapter_title and entry.title:
                    record.chapter_title = entry.title

                next_cid = (
                    target_entries[idx + 1].chapter_id
                    if (idx + 1 < total_in_batch)
                    else ""
                )
                self.storage.append_chapter(record)
                self.checkpoint.mark_completed(entry.chapter_id, record.story_title, next_cid)
                crawled += 1
                self._notify(record, current_num, len(chapter_entries))
            else:
                print(
                    f"\n[Cảnh báo] Bỏ qua chương {entry.chapter_id} "
                    f"({entry.title or 'không rõ tên'}) do không tải được nội dung.",
                    flush=True,
                )

            self._pace(idx)

        return crawled

    # ------------------------------------------------------ navigation mode
    def _run_by_navigation(self) -> int:
        current_chapter_id = self.initial_chapter_id
        if (
            self.checkpoint.next_chapter_id
            and (
                not self.initial_chapter_id
                or self.checkpoint.is_completed(self.initial_chapter_id)
            )
        ):
            current_chapter_id = self.checkpoint.next_chapter_id
        elif (
            self.checkpoint.last_chapter_id
            and (
                not self.initial_chapter_id
                or self.checkpoint.is_completed(self.initial_chapter_id)
            )
        ):
            current_chapter_id = self.checkpoint.last_chapter_id

        if not current_chapter_id:
            current_chapter_id = self.adapter.resolve_first_chapter(self._page, self.ref)

        crawled = 0
        step = 0
        while current_chapter_id:
            if self.max_chapters is not None and crawled >= self.max_chapters:
                break

            if self.checkpoint.is_completed(current_chapter_id) and (self.max_chapters != 1):
                if (
                    self.checkpoint.next_chapter_id
                    and self.checkpoint.next_chapter_id != current_chapter_id
                ):
                    current_chapter_id = self.checkpoint.next_chapter_id
                    continue
                break

            entry = ChapterEntry(
                chapter_id=str(current_chapter_id),
                url=self.adapter.chapter_url(self.ref, str(current_chapter_id)),
            )
            record, next_chapter_id = self._scrape_entry(entry)

            if record:
                self.storage.append_chapter(record)
                self.checkpoint.mark_completed(
                    str(current_chapter_id), record.story_title, next_chapter_id or ""
                )
                crawled += 1
                self._notify(record, crawled)
            else:
                break

            if (
                not next_chapter_id
                or next_chapter_id == "0"
                or next_chapter_id == str(current_chapter_id)
            ):
                break

            current_chapter_id = str(next_chapter_id)
            self._pace(step)
            step += 1

        return crawled

    # -------------------------------------------------------------- helpers
    def _scrape_entry(
        self, entry: ChapterEntry, max_attempts: int = 3
    ) -> Tuple[Optional[ChapterRecord], Optional[str]]:
        """Open + extract one chapter, retrying challenge/network failures."""
        for attempt in range(max_attempts):
            status = self.adapter.open_chapter(self._page, entry, self.ref)

            if status == OPEN_OK:
                return self.adapter.extract(self._page, self.ref, entry)

            if status == OPEN_NO_CONTENT:
                # The URL exists but has no body (removed / placeholder chapter).
                return None, None

            if status == OPEN_CHALLENGE:
                if attempt < max_attempts - 1:
                    cooldown = self.adapter.challenge_cooldown
                    print(
                        f"\n[CF] Bị chặn challenge ở chương {entry.chapter_id}. "
                        f"Chờ {cooldown:.0f}s rồi thử lại (lần {attempt + 2}/{max_attempts})...",
                        flush=True,
                    )
                    time.sleep(cooldown)
                    try:
                        self._page = self.browser_manager.recycle_now()
                    except Exception:
                        pass
                    continue
                return None, None

            # OPEN_ERROR / transient navigation failure
            if attempt < max_attempts - 1:
                time.sleep(2.0 + attempt * 2.0)
                continue
            return None, None

        return None, None

    def _pace(self, completed_index: int) -> None:
        delay = (
            self.delay
            if self.delay is not None
            else random.uniform(self.adapter.delay_min, self.adapter.delay_max)
        )
        if delay:
            time.sleep(delay)

        self._page = self.browser_manager.step_chapter()

        if (
            self.adapter.burst_size
            and (completed_index + 1) % self.adapter.burst_size == 0
            and self.adapter.burst_sleep
        ):
            print(
                f"[~] Nghỉ {self.adapter.burst_sleep:.0f}s sau "
                f"{completed_index + 1} chương để tránh bị chặn...",
                flush=True,
            )
            time.sleep(self.adapter.burst_sleep)

    def _notify(self, record: ChapterRecord, index: int, total: int = 0) -> None:
        if not self.on_chapter_crawled:
            return
        try:
            self.on_chapter_crawled(record, index, total)
        except TypeError:
            self.on_chapter_crawled(record, index)


# Backwards-compatible alias: existing scripts/tests import SangTacVietScraper.
SangTacVietScraper = NovelScraper
