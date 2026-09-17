"""
Unit tests for SangTacViet Scraper components.
"""

import json
from pathlib import Path
import tempfile
import unittest

from checkpoint_manager import CheckpointManager
from models import ChapterRecord, CheckpointData
from scraper import SangTacVietScraper
from storage import JsonlStorage


class TestScraperComponents(unittest.TestCase):
    def test_url_parser(self):
        # Story URL
        scraper = SangTacVietScraper(
            target_url="https://sangtacviet.app/truyen/dich/1/53028/",
            max_chapters=1,
        )
        self.assertEqual(scraper.source, "dich")
        self.assertEqual(scraper.story_id, "53028")
        self.assertIsNone(scraper.initial_chapter_id)

        # Chapter URL
        scraper_chap = SangTacVietScraper(
            target_url="https://sangtacviet.app/truyen/qidian/1/1050478153/924814528/",
            max_chapters=1,
        )
        self.assertEqual(scraper_chap.source, "qidian")
        self.assertEqual(scraper_chap.story_id, "1050478153")
        self.assertEqual(scraper_chap.initial_chapter_id, "924814528")

    def test_checkpoint_lifecycle(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            cm = CheckpointManager("test_story", tmppath)
            self.assertEqual(cm.completed_count, 0)
            self.assertFalse(cm.is_completed("1"))

            # Mark chapter 1 completed
            cm.mark_completed("1", "Test Story Title", next_chapter_id="2")
            self.assertEqual(cm.completed_count, 1)
            self.assertTrue(cm.is_completed("1"))
            self.assertEqual(cm.next_chapter_id, "2")

            # Reload from disk
            cm_reloaded = CheckpointManager("test_story", tmppath)
            self.assertEqual(cm_reloaded.completed_count, 1)
            self.assertTrue(cm_reloaded.is_completed("1"))
            self.assertEqual(cm_reloaded.next_chapter_id, "2")
            self.assertEqual(cm_reloaded.data.story_title, "Test Story Title")

    def test_storage_streaming_append(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            storage = JsonlStorage("test_story", tmppath)

            rec = ChapterRecord(
                story_id="test_story",
                story_title="Sample Title",
                chapter_id="1",
                chapter_title="Chapter 1",
                url="https://example.com/1",
                content_vi="Đoạn văn 1\n\nĐoạn văn 2",
                content_zh="第一段\n\n第二段",
                content_hanviet="Đoạn 1\n\nĐoạn 2",
            )
            storage.append_chapter(rec)

            jsonl_file = tmppath / "test_story.jsonl"
            self.assertTrue(jsonl_file.exists())

            with open(jsonl_file, "r", encoding="utf-8") as f:
                lines = f.readlines()
                self.assertEqual(len(lines), 1)
                obj = json.loads(lines[0])
                self.assertEqual(obj["story_id"], "test_story")
                self.assertEqual(obj["chapter_id"], "1")
                self.assertIn("Đoạn văn 1", obj["content_vi"])


if __name__ == "__main__":
    unittest.main()
