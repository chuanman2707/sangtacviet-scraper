"""
Twkan adapter (twkan.com - Traditional Chinese web novels).

The site sits behind a Cloudflare managed challenge.  CloakBrowser renders it
normally in headless mode; the adapter keeps a human-ish pace and retries when
an interstitial shows up.

Structure:
  * Book page:        https://twkan.com/book/{book_id}.html
  * Chapter index:    https://twkan.com/book/{book_id}/index.html
  * Chapter list API: https://twkan.com/ajax_novels/chapterlist/{book_id}.html
  * Chapter:          https://twkan.com/txt/{book_id}/{chapter_id}
"""

import re
import time
from typing import List, Optional, Tuple
from urllib.parse import urlparse

from config import (
    DEFAULT_PAGE_TIMEOUT_MS,
    TWKAN_BURST_SIZE,
    TWKAN_BURST_SLEEP,
    TWKAN_CHALLENGE_COOLDOWN_SEC,
    TWKAN_CHALLENGE_TIMEOUT_SEC,
    TWKAN_DELAY_MAX,
    TWKAN_DELAY_MIN,
)
from models import ChapterRecord
from textnorm import sanitize_chapter_text

from .base import ChapterEntry, SiteAdapter, StoryRef


TWKAN_EXTRACTION_JS = """() => {
    const box = document.querySelector('#txtcontent0');
    if (!box) return null;

    // Remove ad / tracking nodes before reading the rendered text.
    box.querySelectorAll('ins, script, style, iframe, .txtad, .adsbygoogle').forEach(e => e.remove());

    const h1 = document.querySelector('.txtnav h1');
    const info = window.bookinfo || {};
    const pageLinks = Array.from(document.querySelectorAll('.page1 a'));
    const nextLink = pageLinks.find(a => (a.textContent || '').trim() === '下一章');

    return {
        title: h1 ? (h1.innerText || '').trim() : (info.chaptername || '').trim(),
        story: (info.articlename || '').trim(),
        author: (info.author || '').trim(),
        text: box.innerText || '',
        nextHref: nextLink ? nextLink.href : '',
    };
}"""


class TwkanAdapter(SiteAdapter):
    name = "twkan"
    display_name = "Twkan (台灣小說網)"
    cookie_hosts = ("twkan.com", "www.twkan.com")
    default_cookie_file = "cookies_twkan.json"

    delay_min = TWKAN_DELAY_MIN
    delay_max = TWKAN_DELAY_MAX
    burst_size = TWKAN_BURST_SIZE
    burst_sleep = TWKAN_BURST_SLEEP
    challenge_timeout = TWKAN_CHALLENGE_TIMEOUT_SEC
    challenge_cooldown = TWKAN_CHALLENGE_COOLDOWN_SEC

    # --------------------------------------------------------------- matching
    @classmethod
    def matches(cls, url: str) -> bool:
        parsed = urlparse(url if "://" in url else f"https://{url}")
        host = (parsed.netloc or "").lower()
        return "twkan." in host

    def parse(self, url: str) -> StoryRef:
        parsed = urlparse(url if "://" in url else f"https://{url}")
        host = (parsed.netloc or "twkan.com").lower()
        base_url = f"{parsed.scheme or 'https'}://{host}"
        path = parsed.path or "/"

        story_id = ""
        chapter_id: Optional[str] = None

        m = re.match(r"^/book/(\d+)(?:/index\.html|\.html|/)?$", path)
        if m:
            story_id = m.group(1)
        else:
            m = re.match(r"^/txt/(\d+)/(\d+)", path)
            if m:
                story_id = m.group(1)
                chapter_id = m.group(2)
            else:
                numbers = re.findall(r"\d+", path)
                if not numbers:
                    raise ValueError(
                        f"URL không đúng định dạng Twkan: {url}\n"
                        f"Mẫu hợp lệ: https://twkan.com/book/97278/index.html"
                    )
                story_id = numbers[0]
                if len(numbers) > 1:
                    chapter_id = numbers[1]

        return StoryRef(
            site=self.name,
            base_url=base_url,
            story_id=story_id,
            source="twkan",
            initial_chapter_id=chapter_id,
        )

    # --------------------------------------------------------------- chapters
    def chapter_url(self, ref: StoryRef, chapter_id: str) -> str:
        return f"{ref.base_url}/txt/{ref.story_id}/{chapter_id}"

    @staticmethod
    def parse_chapter_list_html(html: str) -> List[ChapterEntry]:
        """Parse the AJAX chapter-list fragment.

        Each row looks like:
          <li data-num="1"><a href="https://twkan.com/txt/97278/52767726"
              title="第1章 ... 字數：5210 ...">第1章 ...</a></li>
        """
        if not html:
            return []
        entries: List[ChapterEntry] = []
        pattern = re.compile(
            r'<li[^>]*data-num="(\d+)"[^>]*>\s*<a[^>]*href="([^"]+)"[^>]*'
            r'(?:title="([^"]*)")?[^>]*>(.*?)</a>',
            re.DOTALL | re.IGNORECASE,
        )
        for m in pattern.finditer(html):
            order = int(m.group(1))
            href = m.group(2).strip()
            title_attr = (m.group(3) or "").strip()
            inner = re.sub(r"<[^>]+>", "", m.group(4) or "").strip()
            title = inner or re.sub(r"\s*字數：.*$", "", title_attr).strip()
            if not href:
                continue
            chapter_id = href.rstrip("/").split("/")[-1].split("?")[0]
            if not chapter_id.isdigit():
                continue
            entries.append(
                ChapterEntry(
                    chapter_id=chapter_id,
                    title=title,
                    url=href,
                    order=order,
                )
            )
        return entries

    @staticmethod
    def parse_index_links(html: str, base_url: str = "https://twkan.com") -> List[ChapterEntry]:
        """Fallback parser for the book index page (first N visible chapters)."""
        if not html:
            return []
        entries: List[ChapterEntry] = []
        seen = set()
        pattern = re.compile(
            r'<a[^>]*href="(?:' + re.escape(base_url) + r')?(/txt/\d+/(\d+))"[^>]*>(.*?)</a>',
            re.DOTALL | re.IGNORECASE,
        )
        for order, m in enumerate(pattern.finditer(html)):
            chapter_id = m.group(2)
            if chapter_id in seen:
                continue
            seen.add(chapter_id)
            title = re.sub(r"<[^>]+>", "", m.group(3) or "").strip()
            entries.append(
                ChapterEntry(
                    chapter_id=chapter_id,
                    title=title,
                    url=f"{base_url}{m.group(1)}",
                    order=order,
                )
            )
        return entries

    def fetch_chapter_list(self, page, ref: StoryRef) -> List[ChapterEntry]:
        ajax_url = f"{ref.base_url}/ajax_novels/chapterlist/{ref.story_id}.html"

        for attempt in range(2):
            try:
                page.goto(ajax_url, wait_until="domcontentloaded", timeout=DEFAULT_PAGE_TIMEOUT_MS)
                self._wait_for_document(page)
                entries = self.parse_chapter_list_html(page.content())
                if entries:
                    return entries
            except Exception:
                pass
            if attempt == 0:
                time.sleep(2.0)

        # Fallback: scrape the first page of links from the book index.
        try:
            page.goto(
                f"{ref.base_url}/book/{ref.story_id}/index.html",
                wait_until="domcontentloaded",
                timeout=DEFAULT_PAGE_TIMEOUT_MS,
            )
            self._wait_for_document(page)
            return self.parse_index_links(page.content(), ref.base_url)
        except Exception:
            return []

    def _wait_for_document(self, page, timeout: float = 20.0) -> bool:
        """Wait for the challenge (if any) and for the document body to exist."""
        from browser_manager import wait_through_challenge

        wait_through_challenge(page, timeout=timeout, verbose=True)
        start = time.time()
        while time.time() - start < 5.0:
            try:
                if page.evaluate("() => document.body && document.body.children.length > 0"):
                    return True
            except Exception:
                pass
            time.sleep(0.2)
        return False

    # ------------------------------------------------------------------- open
    def wait_content_ready(self, page, timeout: float = 10.0) -> bool:
        start = time.time()
        while time.time() - start < timeout:
            try:
                length = page.evaluate(
                    """() => {
                        const b = document.querySelector('#txtcontent0');
                        return b ? (b.innerText || '').length : 0;
                    }"""
                )
                if length and length > 50:
                    return True
            except Exception:
                pass
            time.sleep(0.25)
        return False

    # ---------------------------------------------------------------- extract
    def extract(
        self, page, ref: StoryRef, entry: ChapterEntry
    ) -> Tuple[Optional[ChapterRecord], Optional[str]]:
        try:
            data = page.evaluate(TWKAN_EXTRACTION_JS)
        except Exception:
            return None, None

        if not data:
            return None, None

        text = sanitize_chapter_text(data.get("text", ""))
        if len(text) < 20:
            return None, None

        chapter_title = (data.get("title") or entry.title or "").strip()
        story_title = (data.get("story") or "").strip()
        if not story_title:
            # e.g. "第1章 ...-故事名-作者-分類-台灣小說網"
            try:
                page_title = page.title()
                parts = page_title.split("-")
                if len(parts) >= 2:
                    story_title = parts[1].strip()
            except Exception:
                story_title = ""

        record = ChapterRecord(
            story_id=ref.story_id,
            story_title=story_title,
            chapter_id=entry.chapter_id,
            chapter_title=chapter_title,
            url=entry.url or self.chapter_url(ref, entry.chapter_id),
            content_vi="",
            content_zh=text,
            content_hanviet="",
            source=self.name,
            language="zh",
        )

        next_chapter_id = self._next_id_from_href(data.get("nextHref", ""), ref)
        return record, next_chapter_id

    def _next_id_from_href(self, href: str, ref: StoryRef) -> Optional[str]:
        if not href:
            return None
        clean = href.strip().rstrip("/")
        parts = clean.split("/")
        if len(parts) >= 2 and parts[-1].isdigit():
            return parts[-1]
        return None
