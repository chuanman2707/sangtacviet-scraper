"""
Unit tests for cleaner.py (NovelCleaner postprocessing).
"""

import unittest
from pathlib import Path
import tempfile
from cleaner import NovelCleaner, parse_chapter_number, clean_markdown_file, clean_jsonl_file


class TestNovelCleaner(unittest.TestCase):
    def setUp(self):
        self.cleaner = NovelCleaner()

    def test_watermark_removal(self):
        text = (
            "@Bạn đang đọc bản lưu trong hệ thống\n\n"
            "Chương 1 mở đầu.\n"
            "@sangtacviet.app\n"
            "Nội dung truyện chính thức."
        )
        cleaned = self.cleaner.clean_text(text)
        self.assertNotIn("@Bạn đang đọc bản lưu trong hệ thống", cleaned)
        self.assertNotIn("@sangtacviet.app", cleaned)
        self.assertIn("Chương 1 mở đầu.", cleaned)
        self.assertIn("Nội dung truyện chính thức.", cleaned)

    def test_convert_error_replacements(self):
        sample = (
            "Tần Giang Quan thượng tá đích tôn môn lẩm bẩm nói.\n"
            "Bốn chín, Chu Chính khán trứ Card Reader không biết như thế nào kiếm tiền.\n"
            "A đang, chúng ta trong tay có bao nhiêu tiền!\n"
            "ngược lại Chu Chính Bỉ so sánh tự nhiên.\n"
            "Tần Giang đối thoại lộ để bụng.\n"
            "Ân.. Trắng lộ!\n"
            "bên trên trách nhiệm trường học làm hiệu trưởng.\n"
            "nhân viên bảo vệ đánh hai cái cửa phòng.\n"
            "Liễu Như Yên cầm nhầm tạp muốn mua quả táo bốn.\n"
            "Đánh ngươi mẹ trái trứng!"
        )
        cleaned = self.cleaner.clean_text(sample)
        self.assertNotIn("Quan thượng tá đích tôn môn", cleaned)
        self.assertIn("đóng cửa phòng hiệu trưởng lại", cleaned)
        self.assertNotIn("khán trứ", cleaned)
        self.assertIn("chăm chú nhìn", cleaned)
        self.assertNotIn("A đang", cleaned)
        self.assertIn("A Chính", cleaned)
        self.assertNotIn("Bỉ so sánh", cleaned)
        self.assertIn("khá là", cleaned)
        self.assertNotIn("đối thoại lộ", cleaned)
        self.assertIn("đối với Bạch Lộ", cleaned)
        self.assertNotIn("Trắng lộ", cleaned)
        self.assertIn("Bạch Lộ", cleaned)
        self.assertNotIn("trách nhiệm trường học", cleaned)
        self.assertIn("trường nghề", cleaned)
        self.assertNotIn("đánh hai cái cửa phòng", cleaned)
        self.assertIn("gõ hai tiếng vào cửa phòng", cleaned)
        self.assertNotIn("cầm nhầm tạp", cleaned)
        self.assertIn("cầm nhầm thẻ", cleaned)
        self.assertNotIn("quả táo bốn", cleaned)
        self.assertIn("iPhone 4", cleaned)
        self.assertNotIn("Đánh ngươi mẹ trái trứng", cleaned)
        self.assertIn("Chuyển con mẹ mày trứng", cleaned)

    def test_parse_chapter_number(self):
        self.assertEqual(parse_chapter_number("Thứ 10 chương Thao trường"), 10)
        self.assertEqual(parse_chapter_number("Thứ 3 chương Liếm chó"), 3)
        self.assertEqual(parse_chapter_number("Chương 5: Khởi đầu"), 5)

    def test_markdown_cleaning_and_deduplication(self):
        md_content = (
            "# Tiêu đề truyện\n\n"
            "- **Mã truyện:** `123`\n\n"
            "---\n\n"
            "## Thứ 10 chương Kết cục\n\n"
            "@Bạn đang đọc bản lưu trong hệ thống\n\n"
            "Nội dung chương 10.\n\n"
            "---\n\n"
            "## Thứ 3 chương Mở đầu\n\n"
            "@Bạn đang đọc bản lưu trong hệ thống\n\n"
            "Nội dung chương 3.\n\n"
            "---\n\n"
            "## Thứ 10 chương Kết cục\n\n"
            "@Bạn đang đọc bản lưu trong hệ thống\n\n"
            "Nội dung chương 10.\n\n"
            "---\n"
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            in_file = Path(tmpdir) / "in.md"
            out_file = Path(tmpdir) / "out.md"
            in_file.write_text(md_content, encoding="utf-8")

            stats = clean_markdown_file(in_file, out_file, self.cleaner)
            self.assertEqual(stats["total"], 3)
            self.assertEqual(stats["unique"], 2)
            self.assertEqual(stats["duplicates"], 1)

            out_text = out_file.read_text(encoding="utf-8")
            self.assertNotIn("@Bạn đang đọc bản lưu trong hệ thống", out_text)
            # Ensure Chương 3 comes before Chương 10
            idx_3 = out_text.find("Thứ 3 chương")
            idx_10 = out_text.find("Thứ 10 chương")
            self.assertTrue(idx_3 != -1 and idx_10 != -1 and idx_3 < idx_10)


if __name__ == "__main__":
    unittest.main()
