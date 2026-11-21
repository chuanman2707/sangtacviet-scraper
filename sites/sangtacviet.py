"""SangTacViet adapter (Vietnamese / convert sources, VIP aware)."""

import json
import time
from pathlib import Path
from typing import List, Optional, Tuple
from urllib.parse import urlparse

from config import (
    DEFAULT_CONTENT_WAIT_TIMEOUT_SEC,
    DEFAULT_PAGE_TIMEOUT_MS,
)
from extractor import extract_chapter_payload
from models import ChapterRecord

from .base import ChapterEntry, SiteAdapter, StoryRef


STV_HOSTS = (
    "14.225.254.182",
    "sangtacviet.vip",
    "sangtacviet.app",
    "sangtacviet.com",
)


class SangTacVietAdapter(SiteAdapter):
    name = "sangtacviet"
    display_name = "SangTacViet"
    cookie_hosts = STV_HOSTS
    default_cookie_file = "cookies.json"

    delay_min = 10.0
    delay_max = 10.0
    burst_size = 0
    challenge_timeout = 25.0
    challenge_cooldown = 10.0

    # SangTacViet's read-captcha is handled inside wait_content_ready().
    detect_challenge = False

    # --------------------------------------------------------------- matching
    @classmethod
    def matches(cls, url: str) -> bool:
        parsed = urlparse(url if "://" in url else f"https://{url}")
        host = (parsed.netloc or "").lower()
        if any(d in host for d in ("sangtacviet", "14.225.254.182")):
            return True
        return parsed.path.startswith("/truyen/")

    def parse(self, url: str) -> StoryRef:
        """
        SangTacViet URL structure:
        - Story:   http://14.225.254.182/truyen/{source}/1/{story_id}/
        - Chapter: https://sangtacviet.app/truyen/{source}/1/{story_id}/{chapter_id}/
        """
        parsed = urlparse(url)
        path = parsed.path.strip("/")
        parts = path.split("/")

        if "14.225.254.182" in parsed.netloc or not parsed.netloc:
            base_url = "https://sangtacviet.vip"
        else:
            base_url = f"{parsed.scheme}://{parsed.netloc}"

        if len(parts) >= 4 and parts[0] == "truyen":
            source = parts[1]
            story_id = parts[3]
            chapter_id = parts[4] if len(parts) >= 5 and parts[4] and parts[4] != "0" else None
            return StoryRef(
                site=self.name,
                base_url=base_url,
                story_id=story_id,
                source=source,
                initial_chapter_id=chapter_id,
            )

        raise ValueError(
            f"URL không đúng định dạng SangTacViet: {url}\n"
            f"Mẫu hợp lệ: https://sangtacviet.app/truyen/dich/1/53028/ hoặc kèm chapter id"
        )

    # --------------------------------------------------------------- chapters
    def chapter_url(self, ref: StoryRef, chapter_id: str) -> str:
        return f"{ref.base_url}/truyen/{ref.source}/1/{ref.story_id}/{chapter_id}/"

    def fetch_chapter_list(self, page, ref: StoryRef) -> List[ChapterEntry]:
        """Fetch the full ordered chapter list from the site's AJAX endpoint."""
        story_url = f"{ref.base_url}/truyen/{ref.source}/1/{ref.story_id}/"
        try:
            page.goto(story_url, wait_until="domcontentloaded", timeout=DEFAULT_PAGE_TIMEOUT_MS)
            time.sleep(1.0)
            api_url = (
                f"/index.php?ngmar=chapterlist&h={ref.source}"
                f"&bookid={ref.story_id}&sajax=getchapterlist"
            )
            data = page.evaluate(
                f"""async () => {{
                    try {{
                        const r = await fetch('{api_url}');
                        const j = await r.json();
                        if (j && j.data) return j.data;
                    }} catch (e) {{}}
                    return null;
                }}"""
            )
            if not data:
                return []

            entries: List[ChapterEntry] = []
            for order, item in enumerate(str(data).split("-//-")):
                parts = item.split("-/-")
                if len(parts) >= 3:
                    entries.append(ChapterEntry(parts[1].strip(), parts[2].strip(), order=order))
                elif len(parts) >= 2:
                    entries.append(ChapterEntry(parts[1].strip(), "", order=order))
            return entries
        except Exception:
            return []

    def resolve_first_chapter(self, page, ref: StoryRef) -> Optional[str]:
        chapters = self.fetch_chapter_list(page, ref)
        if chapters:
            return chapters[0].chapter_id

        story_url = f"{ref.base_url}/truyen/{ref.source}/1/{ref.story_id}/"
        try:
            page.goto(story_url, wait_until="domcontentloaded", timeout=DEFAULT_PAGE_TIMEOUT_MS)
            time.sleep(1.0)
            first_id = page.evaluate(
                """() => {
                    const el = document.querySelector(".listchapitem, a[id]");
                    if (el && el.id && /^\\d+$/.test(el.id)) return el.id;
                    if (el && el.getAttribute("onclick")) {
                        const m = el.getAttribute("onclick").match(/\\d+/);
                        if (m) return m[0];
                    }
                    return null;
                }"""
            )
            if first_id:
                return str(first_id)
        except Exception:
            pass
        return "1"

    # ------------------------------------------------------------------- open
    def wait_content_ready(self, page, timeout: float = DEFAULT_CONTENT_WAIT_TIMEOUT_SEC) -> bool:
        start_wait = time.time()
        captcha_notified = False
        wait_timeout = timeout

        while time.time() - start_wait < wait_timeout:
            time.sleep(0.3)
            try:
                cnt = page.evaluate("() => document.querySelectorAll('i[t]').length")
                if cnt and cnt > 50:
                    return True

                has_captcha = page.evaluate(
                    """() => {
                        const c = document.querySelector("#captcha");
                        return c && c.offsetParent !== null;
                    }"""
                )
                if has_captcha:
                    wait_timeout = max(wait_timeout, 45.0)
                    if not captcha_notified:
                        print(
                            "\n[!] Đang chờ xác nhận Captcha đọc truyện trên trình duyệt "
                            "(chỉ cần bấm 1 lần duy nhất)...",
                            flush=True,
                        )
                        captcha_notified = True
                    try:
                        for f in page.frames:
                            if any(k in f.url for k in ("cloudflare", "turnstile", "challenge")):
                                f.click(
                                    "input[type=checkbox], #challenge-stage, .ctp-checkbox-label",
                                    timeout=500,
                                )
                    except Exception:
                        pass
                elif time.time() - start_wait > 2.0:
                    page.evaluate("() => typeof gotox === 'function' && gotox()")
                    try:
                        page.click("#maincontent", timeout=500)
                    except Exception:
                        pass
            except Exception:
                continue

        if captcha_notified:
            try:
                cookies = page.context.cookies()
                Path("cookies.json").write_text(
                    json.dumps(cookies, ensure_ascii=False, indent=2), encoding="utf-8"
                )
            except Exception:
                pass
        return False

    # ---------------------------------------------------------------- extract
    def extract(
        self, page, ref: StoryRef, entry: ChapterEntry
    ) -> Tuple[Optional[ChapterRecord], Optional[str]]:
        try:
            record, next_chapter_id = extract_chapter_payload(
                page,
                ref.story_id,
                entry.chapter_id,
                entry.url or self.chapter_url(ref, entry.chapter_id),
                extract_bilingual=self.extract_bilingual,
            )
        except Exception:
            return None, None

        if record:
            record.source = self.name
            record.language = "vi"
            if not record.chapter_title and entry.title:
                record.chapter_title = entry.title
            # Sequential fallback for numeric chapter ids when the DOM next link is missing.
            if (
                (not next_chapter_id or next_chapter_id == "0")
                and entry.chapter_id.isdigit()
                and len(entry.chapter_id) <= 6
            ):
                next_chapter_id = str(int(entry.chapter_id) + 1)
        return record, next_chapter_id
