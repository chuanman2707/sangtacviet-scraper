#!/usr/bin/env python3
"""
Postprocessing & Text Cleaner for Crawled Web Novels (SangTacViet & Chinese-Vietnamese Convert).
Cleans anti-bot watermarks, deduplicates chapters, sorts chronological order,
normalizes formatting, and polishes raw Chinese-Vietnamese machine translation.
"""

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# ==============================================================================
# 1. WATERMARKS & JUNK PATTERNS
# ==============================================================================
WATERMARK_PATTERNS = [
    re.compile(r"^@.*bản lưu.*", re.IGNORECASE),
    re.compile(r"^@.*hệ thống.*", re.IGNORECASE),
    re.compile(r"^@\S+.*", re.IGNORECASE),
    re.compile(r".*sangtacviet\.(app|com|vip|net).*", re.IGNORECASE),
    re.compile(r".*tangthuvien\.(vn|com).*", re.IGNORECASE),
    re.compile(r".*truyenchu\.(vn|com).*", re.IGNORECASE),
    re.compile(r".*truyencv\.(vn|com).*", re.IGNORECASE),
    re.compile(r".*wikidich\.(com|net).*", re.IGNORECASE),
    re.compile(r".*bachngocsach\.(com|net).*", re.IGNORECASE),
    re.compile(r"^\s*bản convert được thực hiện bởi:?.*", re.IGNORECASE),
    re.compile(r"^\s*chúc bạn đọc truyện vui vẻ.*", re.IGNORECASE),
    re.compile(r"^\s*bấm like để ủng hộ.*", re.IGNORECASE),
]

# Kaomoji / Emoticons to replace or clean
KAOMOJI_MAP = {
    r"\(\s*ﾉ\s*´д`\s*\)": "(thở dài bất lực)",
    r"\(●･̆⍛･̆●\)": "(ngơ ngác)",
}

# ==============================================================================
# 2. CONVERT / MACHINE TRANSLATION POLISH DICTIONARY
# ==============================================================================
CONVERT_REPLACEMENTS = [
    # Severe convert errors & funny mistranslations
    (r"Tần Giang Quan thượng tá đích tôn môn", "Tần Giang đóng cửa phòng hiệu trưởng lại,"),
    (r"Quan thượng tá đích tôn môn", "Đóng cửa phòng hiệu trưởng lại"),
    (r"quan thượng tá đích tôn môn", "đóng cửa phòng hiệu trưởng lại"),
    (r"tá đích tôn môn", "cửa phòng hiệu trưởng"),
    (r"\bBỉ so sánh\b", "khá là"),
    (r"\bbỉ so sánh\b", "khá là"),
    (r"\bA đang\b", "A Chính"),
    (r"\bkhán trứ\b", "chăm chú nhìn"),
    (r"\bKhán trứ\b", "Nhìn"),
    (r"\bnhìn lấy\b", "nhìn"),
    (r"\bNhìn lấy\b", "Nhìn"),
    
    # Character names corrupted by dictionary splitter
    (r"đối thoại lộ", "đối với Bạch Lộ"),
    (r"Đối thoại lộ", "Đối với Bạch Lộ"),
    (r"Ân\.\.\s*Trắng lộ!", "Ừm... Bạch Lộ!"),
    (r"\bTrắng lộ\b", "Bạch Lộ"),
    (r"\btrắng lộ\b", "Bạch Lộ"),
    (r"\bvệ bão tố\b", "Vệ Bão Tố"),
    (r"\bVệ bão tố\b", "Vệ Bão Tố"),
    (r"\bBốn chín\b", "Tứ Cửu"),
    (r"\bbốn chín\b", "Tứ Cửu"),
    
    # Location & school terms
    (r"phá trách nhiệm trường học", "trường nghề tồi tàn"),
    (r"trách nhiệm trường học", "trường nghề"),
    (r"Trách nhiệm trường học", "Trường nghề"),
    (r"Khứ đại học", "sang trường đại học"),
    (r"khứ đại học", "sang trường đại học"),
    
    # Numbers, years & currency
    (r"(\d{4})\s*năm", r"Năm \1"),
    (r"\b(\d+)\s*nguyên\b", r"\1 tệ"),
    (r"\bNăm nguyên\b", "Năm tệ"),
    (r"\bnăm nguyên\b", "năm tệ"),
    (r"quả táo bốn", "iPhone 4"),
    (r"Quả táo bốn", "iPhone 4"),
    (r"nghiệm cơ", "kiểm tra máy"),
    (r"cầm nhầm tạp", "cầm nhầm thẻ"),
    (r"đi lấy tạp", "đi lấy thẻ"),
    (r"nhầm tạp", "nhầm thẻ"),
    (r"lấy tạp", "lấy thẻ"),
    (r"sai tạp", "nhầm thẻ"),
    (r"xoát thẻ", "quẹt thẻ"),
    (r"quét thẻ", "quẹt thẻ"),
    (r"xoát không ra tiền", "quẹt thẻ không ra tiền"),
    
    # Street slangs & contemporary buzzwords
    (r"làm bài hai người", "hai người dẫn đầu"),
    (r"kinh ngạc giả", "người kinh ngạc"),
    (r"Đậu Đậu giày", "Giày đậu đậu"),
    (r"đậu đậu giày", "giày đậu đậu"),
    (r"Khốc đập chết", "Ngầu chết đi được"),
    (r"khốc đập chết", "ngầu chết đi được"),
    (r"kéo đen một con rồng", "cho vào danh sách đen một mạch"),
    (r"bản cơ từ đại", "mặc định theo máy"),
    (r"lập bài phường nữ tử", "loại phụ nữ lẳng lơ còn đòi lập đền thờ trinh tiết"),
    (r"lập bài phường", "lập đền thờ trinh tiết"),
    (r"thiết lập nhân vật", "hình tượng nhân vật"),
    (r"Đánh ngươi mẹ trái trứng", "Chuyển con mẹ mày trứng"),
    (r"đánh ngươi mẹ trái trứng", "chuyển con mẹ mày trứng"),
    (r"Lâm Lâm dù sao cuối cùng", "Gom góp lặt vặt lại"),
    (r"ngươi kéo không hớt tóc", "ngươi còn không chịu cắt tóc à"),
    (r"thực phẩm giãy đến", "thực phẩm kiếm được"),
    (r"giãy đến", "kiếm được"),
    (r"thương mua", "tiệm tạp hóa"),
    (r"tựa ở trường học ký túc xá", "dựa vào ký túc xá trường học"),
    (r"thay người đổi mới hoàn toàn ba vị diện lỗ", "ba gương mặt hoàn toàn đổi mới"),
    (r"đổi mới hoàn toàn ba vị diện lỗ", "ba gương mặt hoàn toàn đổi mới"),
    (r"đánh hai cái cửa phòng", "gõ hai tiếng vào cửa phòng"),
    (r"không dưới đồ vật", "không tải thứ gì"),
    (r"phiêu phì thể tráng", "to béo vạm vỡ"),
    (r"đại quang đầu", "đầu trọc lốc"),
    (r"tặc mi thử nhãn", "mắt lấm lét như chuột"),
    (r"tinh khiết bại hoại", "đúng là cặn bã thuần túy"),
    (r"rút cái nào môn phong", "phát rồ cái gì"),
    (r"bán hàng sau đài", "sau quầy thu ngân"),
    (r"đưa tặng", "tặng kèm"),
    (r"\bnâng đỡ\b", "hỗ trợ"),
    (r"triển khai trừ", "khai trừ đuổi học"),
    (r"không ràng buộc sử dụng", "sử dụng miễn phí"),
    (r"lẩm bẩm", "lẩm bẩm"),
    
    # Grammatical structure: "phía dưới" (一下 - một chút / một lát / sơ qua)
    (r"sững sờ phía dưới", "sững sờ một lát"),
    (r"suy xét phía dưới", "suy nghĩ một lát"),
    (r"bố trí phía dưới", "bố trí sơ qua"),
    (r"nhìn nhiều hai mắt", "nhìn kỹ thêm hai lần"),
    (r"thân thân thể", "thân mình"),
    (r"thân thân quần áo", "kéo kéo lại quần áo"),
]

# Proper nouns that must NEVER be lowercased when merging sentences
PROPER_NAMES = {
    "Tần Giang", "Chu Chính", "Bạch Lộ", "Tứ Cửu", "Liễu Như Yên", "Ngô Nhạc",
    "Lục Dao", "Lục Ngọc", "Vương Thao", "Lưu Lệ Lệ", "Vệ Bão Tố", "Hắc Long",
    "Giang ca", "Hongkong", "Hàng Châu", "Nghĩa Ô", "Tùng Hoa", "Tùng Giang",
    "Mộc huyện", "Đông ca", "Card Reader", "iPhone 4"
}


class NovelCleaner:
    def __init__(self, remove_emoticons: bool = False, merge_short_lines: bool = True):
        self.remove_emoticons = remove_emoticons
        self.merge_short_lines = merge_short_lines

    def clean_text(self, text: str) -> str:
        """Pipeline to clean, normalize, and polish Vietnamese novel text."""
        lines = text.split("\n")
        cleaned_lines = []

        for line in lines:
            stripped = line.strip()
            # 1. Skip watermark lines
            if self._is_watermark(stripped):
                continue
            cleaned_lines.append(stripped)

        # Join lines back to work with paragraph blocks
        content = "\n".join(cleaned_lines)

        # 2. Normalize Kaomoji / Emoticons
        for pattern, replacement in KAOMOJI_MAP.items():
            rep = "" if self.remove_emoticons else replacement
            content = re.sub(pattern, rep, content)

        # 3. Apply convert replacements (glossary fixes)
        for pattern, replacement in CONVERT_REPLACEMENTS:
            content = re.sub(pattern, replacement, content)

        # 4. Punctuation & whitespace normalization
        content = self._normalize_punctuation(content)

        # 5. Merge fragmented lines if enabled
        if self.merge_short_lines:
            content = self._smooth_paragraphs(content)

        # Final pass on whitespace
        content = re.sub(r"\n{3,}", "\n\n", content)
        return content.strip()

    def _is_watermark(self, line: str) -> bool:
        if not line:
            return False
        for pat in WATERMARK_PATTERNS:
            if pat.match(line):
                return True
        return False

    def _normalize_punctuation(self, text: str) -> str:
        # Normalize ellipses (e.g. ..... -> ...)
        text = re.sub(r"\.{4,}", "...", text)
        text = re.sub(r"…{2,}", "...", text)

        # Fix spacing around brackets
        text = re.sub(r"\(\s+", "(", text)
        text = re.sub(r"\s+\)", ")", text)
        text = re.sub(r"【\s+", "【", text)
        text = re.sub(r"\s+】", "】", text)

        # Fix space before punctuation marks: , . : ; ! ? (horizontal whitespace only)
        text = re.sub(r"[ \t]+([,.:;!?])", r"\1", text)

        # Ensure space after punctuation if followed immediately by a word (avoiding ellipsis)
        text = re.sub(r"([,:;!?])([A-Za-zÀ-ỹ])", r"\1 \2", text)
        text = re.sub(r"(?<!\.)\.(?!\.)([A-Za-zÀ-ỹ])", r". \1", text)

        # Replace 3 or more blank lines with exactly two newlines
        text = re.sub(r"\n{3,}", "\n\n", text)

        return text

    def _smooth_paragraphs(self, text: str) -> str:
        """
        Merge isolated 1-2 word starter fragments that belong to the following sentence,
        while strictly preserving dialog quotes, scene dividers, and proper noun capitalization.
        """
        paragraphs = text.split("\n\n")
        smoothed = []
        buffer = []

        # Connective / sentence starter words that often get broken into standalone lines
        standalone_starters = {
            "đột nhiên", "giờ phút này", "ít nhất", "điểm này", "hết thảy",
            "hồi lâu", "cho nên", "dưới lầu", "ban đêm", "ở giữa", "lập tức",
            "còn có", "hôm nay", "đúng vào lúc này"
        }

        for p in paragraphs:
            p_strip = p.strip()
            if not p_strip:
                continue

            # Scene breaks or Markdown headers
            if p_strip.startswith(("#", "---", "* * *", "```")) or p_strip in ("...", "……"):
                if buffer:
                    smoothed.append(" ".join(buffer))
                    buffer = []
                smoothed.append(p_strip)
                continue

            # Direct dialogue or bracket announcements should remain distinct
            if p_strip.startswith(("“", '"', "‘", "'", "【", "- ", "* ")):
                if buffer:
                    smoothed.append(" ".join(buffer))
                    buffer = []
                smoothed.append(p_strip)
                continue

            # Check if current paragraph is a very short fragment or starter
            clean_starter_check = p_strip.rstrip(".,!:;…!").strip().lower()
            if clean_starter_check in standalone_starters and len(p_strip.split()) <= 4:
                # Accumulate with buffer
                if buffer:
                    smoothed.append(" ".join(buffer))
                    buffer = []
                # Strip all trailing punctuation from starter
                clean_starter = p_strip.rstrip(".,!:;…!").strip()
                buffer.append(clean_starter)
                continue

            if buffer:
                starter = buffer.pop(0)
                # Check if first word of p_strip is a proper noun
                is_proper = any(p_strip.startswith(name) for name in PROPER_NAMES)
                if not is_proper and p_strip[0].isupper() and not p_strip.startswith(("I", "A ")):
                    # Lowercase only first letter if it's a regular word
                    p_clean = p_strip[0].lower() + p_strip[1:]
                else:
                    p_clean = p_strip

                combined = f"{starter}, {p_clean}"
                smoothed.append(combined)
            else:
                smoothed.append(p_strip)

        if buffer:
            smoothed.append(" ".join(buffer))

        return "\n\n".join(smoothed)


def parse_chapter_number(title: str) -> int:
    """Extract integer chapter number from titles like 'Thứ 10 chương...', 'Chương 5...'"""
    m = re.search(r"(?:thứ|chương)\s*(\d+)", title, re.IGNORECASE)
    if m:
        return int(m.group(1))
    m2 = re.search(r"\b(\d+)\b", title)
    if m2:
        return int(m2.group(1))
    return 999999


def clean_markdown_file(input_file: Path, output_file: Path, cleaner: NovelCleaner) -> Dict:
    """Clean a Markdown novel file, deduplicating and sorting chapters."""
    text = input_file.read_text(encoding="utf-8")

    # Regex for chapter headings (## Chapter Title)
    chap_regex = re.compile(r"^##\s+(.+)$", re.MULTILINE)
    matches = list(chap_regex.finditer(text))

    if not matches:
        cleaned_content = cleaner.clean_text(text)
        output_file.write_text(cleaned_content, encoding="utf-8")
        return {"total": 1, "unique": 1, "duplicates": 0}

    # Extract header metadata before the first chapter
    raw_header = text[: matches[0].start()].strip()
    # Normalize header: clean out duplicate '---'
    header_lines = [l.strip() for l in raw_header.split("\n") if l.strip() and l.strip() != "---"]
    header_text = "\n\n".join(header_lines)

    seen_hashes = set()
    unique_chapters = []
    dup_count = 0

    for i, m in enumerate(matches):
        title = m.group(1).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        raw_body = text[start:end].strip()

        # Clean body
        cleaned_body = cleaner.clean_text(raw_body)
        cleaned_title = cleaner.clean_text(title)

        # Deduplication check by hash of cleaned content
        body_hash = hashlib.md5(cleaned_body.encode("utf-8")).hexdigest()
        if body_hash in seen_hashes:
            dup_count += 1
            continue

        seen_hashes.add(body_hash)
        chap_num = parse_chapter_number(cleaned_title)
        unique_chapters.append({
            "num": chap_num,
            "title": cleaned_title,
            "body": cleaned_body
        })

    # Sort chapters in ascending order by chapter number
    unique_chapters.sort(key=lambda c: c["num"])

    # Reassemble document
    out_parts = []
    if header_text:
        out_parts.append(header_text)

    for chap in unique_chapters:
        out_parts.append(f"## {chap['title']}\n\n{chap['body']}")

    output_content = "\n\n---\n\n".join(out_parts).strip() + "\n"
    output_file.write_text(output_content, encoding="utf-8")

    return {
        "total": len(matches),
        "unique": len(unique_chapters),
        "duplicates": dup_count,
        "sorted_chapters": [c["title"] for c in unique_chapters]
    }


def clean_jsonl_file(input_file: Path, output_file: Path, cleaner: NovelCleaner) -> Dict:
    """Clean a JSONL novel file, deduplicating and sorting records."""
    records = []
    with open(input_file, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))

    seen_hashes = set()
    unique_records = []
    dup_count = 0

    for r in records:
        content_vi = r.get("content_vi", "")
        title = r.get("chapter_title", "")
        
        cleaned_vi = cleaner.clean_text(content_vi)
        cleaned_title = cleaner.clean_text(title)

        h = hashlib.md5(cleaned_vi.encode("utf-8")).hexdigest()
        if h in seen_hashes:
            dup_count += 1
            continue

        seen_hashes.add(h)
        r["content_vi"] = cleaned_vi
        r["chapter_title"] = cleaned_title
        r["_chap_num"] = parse_chapter_number(cleaned_title)
        unique_records.append(r)

    # Sort by chapter number
    unique_records.sort(key=lambda x: x["_chap_num"])
    for r in unique_records:
        r.pop("_chap_num", None)

    with open(output_file, "w", encoding="utf-8") as f:
        for r in unique_records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    return {
        "total": len(records),
        "unique": len(unique_records),
        "duplicates": dup_count,
        "sorted_chapters": [r["chapter_title"] for r in unique_records]
    }


def main():
    parser = argparse.ArgumentParser(description="Clean, deduplicate, and polish novel text.")
    parser.add_argument("--input", "-i", required=True, help="Input .md or .jsonl file path")
    parser.add_argument("--output", "-o", help="Output file path (default: {input}_clean.{ext})")
    parser.add_argument("--no-merge", action="store_true", help="Disable merging fragmented sentences")
    parser.add_argument("--strip-emoticons", action="store_true", help="Completely strip emoticons/kaomoji")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: Input file {input_path} does not exist.")
        sys.exit(1)

    ext = input_path.suffix.lower()
    if not args.output:
        output_path = input_path.parent / f"{input_path.stem}_clean{ext}"
    else:
        output_path = Path(args.output)

    cleaner = NovelCleaner(
        remove_emoticons=args.strip_emoticons,
        merge_short_lines=not args.no_merge
    )

    print(f"[+] Processing {input_path} -> {output_path}...")
    if ext == ".md":
        stats = clean_markdown_file(input_path, output_path, cleaner)
    elif ext == ".jsonl":
        stats = clean_jsonl_file(input_path, output_path, cleaner)
    else:
        raw = input_path.read_text(encoding="utf-8")
        cleaned = cleaner.clean_text(raw)
        output_path.write_text(cleaned, encoding="utf-8")
        stats = {"total": 1, "unique": 1, "duplicates": 0}

    print(f"[✓] Completed!")
    print(f"    Total chapters in input: {stats.get('total')}")
    print(f"    Unique chapters retained: {stats.get('unique')}")
    print(f"    Duplicate chapters removed: {stats.get('duplicates')}")
    if "sorted_chapters" in stats:
        print("    Chronological chapter order:")
        for t in stats["sorted_chapters"]:
            print(f"      - {t}")


if __name__ == "__main__":
    main()
