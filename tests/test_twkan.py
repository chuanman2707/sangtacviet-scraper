"""Unit tests for the Twkan adapter and Chinese text handling."""

import tempfile
import unittest
from pathlib import Path

from cleaner import NovelCleaner, parse_chapter_number
from models import ChapterRecord
from sites.twkan import TwkanAdapter
from storage import JsonlStorage
from textnorm import fold_obfuscated, sanitize_chapter_text


class TestTwkanParser(unittest.TestCase):
    def setUp(self):
        self.adapter = TwkanAdapter()

    def test_parse_book_index(self):
        ref = self.adapter.parse("https://twkan.com/book/97278/index.html")
        self.assertEqual(ref.site, "twkan")
        self.assertEqual(ref.base_url, "https://twkan.com")
        self.assertEqual(ref.story_id, "97278")
        self.assertIsNone(ref.initial_chapter_id)

    def test_parse_book_short_url(self):
        ref = self.adapter.parse("https://twkan.com/book/97278.html")
        self.assertEqual(ref.story_id, "97278")

    def test_parse_chapter_url(self):
        ref = self.adapter.parse("https://twkan.com/txt/97278/52767726")
        self.assertEqual(ref.story_id, "97278")
        self.assertEqual(ref.initial_chapter_id, "52767726")

    def test_matches(self):
        self.assertTrue(TwkanAdapter.matches("https://twkan.com/book/1/index.html"))
        self.assertFalse(TwkanAdapter.matches("https://sangtacviet.vip/truyen/dich/1/2/"))

    def test_chapter_url(self):
        ref = self.adapter.parse("https://twkan.com/book/97278/index.html")
        self.assertEqual(
            self.adapter.chapter_url(ref, "52767726"),
            "https://twkan.com/txt/97278/52767726",
        )

    def test_parse_chapter_list_html(self):
        html = (
            '<ul><li data-num="1"><a href="https://twkan.com/txt/97278/52767726" '
            'title="第1章 瘟神橫空出世 字數：5210 更新時間：2025-12-19">第1章 瘟神橫空出世 </a>'
            "</li>"
            '<li data-num="2"><a href="https://twkan.com/txt/97278/52767727" '
            'title="第2章 大嫂，我來了 字數：4430">第2章 大嫂，我來了 </a></li></ul>'
        )
        entries = TwkanAdapter.parse_chapter_list_html(html)
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0].chapter_id, "52767726")
        self.assertEqual(entries[0].title, "第1章 瘟神橫空出世")
        self.assertEqual(entries[1].order, 2)


class TestTwkanText(unittest.TestCase):
    def test_fold_obfuscated_math_letters(self):
        self.assertEqual(fold_obfuscated("𝕥𝕨𝕜𝕒𝕟.𝕔𝕠𝕞"), "twkan.com")
        self.assertEqual(fold_obfuscated("🆃🆆🅺🅰🅽"), "TWKAN")

    def test_sanitize_removes_watermarks(self):
        raw = (
            "\u3000\u3000第一段正文。\n\n"
            "\u3000\u3000本書由𝕥𝕨𝕜𝕒𝕟.𝕔𝕠𝕞全網首發\n\n"
            "\u3000\u3000【記住本站域名 追台灣小說就上台灣小說網，🆃🆆🅺🅰🅽.🅲🅾🅼超實用 】\n\n"
            "\u3000\u3000GOOGLE搜索TWKAN\n\n"
            "\u3000\u3000第二段正文。"
        )
        cleaned = sanitize_chapter_text(raw)
        self.assertIn("第一段正文", cleaned)
        self.assertIn("第二段正文", cleaned)
        for marker in ("twkan", "TWKAN", "首發", "台灣小說網", "GOOGLE"):
            self.assertNotIn(marker, cleaned)

    def test_cleaner_keeps_chinese_paragraphs(self):
        cleaner = NovelCleaner(merge_short_lines=True)
        raw = "第一段。\n\n本書由𝕥𝕨𝕜𝕒𝕟.𝕔𝕠𝕞全網首發\n\n第二段。"
        cleaned = cleaner.clean_text(raw)
        self.assertEqual(cleaned, "第一段。\n\n第二段。")

    def test_parse_chinese_chapter_number(self):
        self.assertEqual(parse_chapter_number("第12章 完美的邏輯自洽"), 12)
        self.assertEqual(parse_chapter_number("第 3 話"), 3)


class TestTwkanStorage(unittest.TestCase):
    def test_jsonl_markdown_falls_back_to_chinese(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = JsonlStorage("97278", Path(tmpdir))
            record = ChapterRecord(
                story_id="97278",
                story_title="這個臥底，業界口碑很差",
                chapter_id="52767726",
                chapter_title="第1章 瘟神橫空出世",
                url="https://twkan.com/txt/97278/52767726",
                content_vi="",
                content_zh="中文正文。",
                source="twkan",
                language="zh",
            )
            storage.append_chapter(record)
            md = (Path(tmpdir) / "97278.md").read_text(encoding="utf-8")
            self.assertIn("中文正文。", md)


if __name__ == "__main__":
    unittest.main()
