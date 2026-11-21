"""
Lightweight text utilities shared by the extractors and the post-processing
cleaner.  This module intentionally has NO third-party dependencies so that
``cleaner.py`` can keep running as a standalone CLI.

It handles the two obfuscation tricks used by Twkan watermarks:

  * Mathematical alphanumeric symbols:  𝕥𝕨𝕜𝕒𝕟.𝕔𝕠𝕞
  * Enclosed / squared alphanumerics:   🆃🆆🅺🅰🅽.🅲🅾🅼

Both are folded back to plain ASCII before watermark detection, so a single
``twkan`` check catches every variant.
"""

import re
from typing import Optional

# ---------------------------------------------------------------------------
# Unicode obfuscation folding
# ---------------------------------------------------------------------------

_MATH_BLOCKS = [
    # (start of 'A'..'Z', start of lowercase 'a'..'z')
    (0x1D400, 0x1D41A),  # bold
    (0x1D434, 0x1D44E),  # italic
    (0x1D468, 0x1D482),  # bold italic
    (0x1D49C, 0x1D4B6),  # script
    (0x1D4D0, 0x1D4EA),  # bold script
    (0x1D504, 0x1D51E),  # fraktur
    (0x1D538, 0x1D552),  # double-struck
    (0x1D56C, 0x1D586),  # bold fraktur
    (0x1D5A0, 0x1D5BA),  # sans-serif
    (0x1D5D4, 0x1D5EE),  # sans-serif bold
    (0x1D608, 0x1D622),  # sans-serif italic
    (0x1D63C, 0x1D656),  # sans-serif bold italic
    (0x1D670, 0x1D68A),  # monospace
]

_MATH_DIGIT_BLOCKS = [
    0x1D7CE,  # bold
    0x1D7D8,  # double-struck
    0x1D7E2,  # sans-serif
    0x1D7EC,  # sans-serif bold
    0x1D7F6,  # monospace
]

# A few letter-like symbols that live outside the mathematical blocks.
_SPECIAL_LETTERS = {
    0x2102: "C", 0x210D: "H", 0x2115: "N", 0x2119: "P",
    0x211A: "Q", 0x211D: "R", 0x2124: "Z",
}


def _fold_codepoint(cp: int) -> Optional[str]:
    if 0x1F170 <= cp <= 0x1F189:  # squared A-Z (🅰 🆃 🆆 ...)
        return chr(ord("A") + cp - 0x1F170)
    if 0x24B6 <= cp <= 0x24CF:  # circled A-Z
        return chr(ord("A") + cp - 0x24B6)
    if 0x24D0 <= cp <= 0x24E9:  # circled a-z
        return chr(ord("a") + cp - 0x24D0)
    if cp in _SPECIAL_LETTERS:
        return _SPECIAL_LETTERS[cp]

    for upper_start, lower_start in _MATH_BLOCKS:
        if upper_start <= cp < upper_start + 26:
            return chr(ord("A") + cp - upper_start)
        if lower_start <= cp < lower_start + 26:
            return chr(ord("a") + cp - lower_start)

    for start in _MATH_DIGIT_BLOCKS:
        if start <= cp < start + 10:
            return chr(ord("0") + cp - start)

    return None


def fold_obfuscated(text: str) -> str:
    """Map stylised Unicode letters/digits back to plain ASCII."""
    if not text:
        return ""
    out = []
    for ch in text:
        cp = ord(ch)
        if cp < 0x2100:
            out.append(ch)
            continue
        folded = _fold_codepoint(cp)
        out.append(folded if folded is not None else ch)
    return "".join(out)


# ---------------------------------------------------------------------------
# Whitespace / CJK helpers
# ---------------------------------------------------------------------------

# Ideographic space, en/em spaces, NBSP, zero-width characters.
_ODD_SPACES = re.compile(r"[\u00a0\u1680\u2000-\u200d\u202f\u205f\u2060\u3000\ufeff]")
CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")


def normalize_spaces(text: str) -> str:
    """Collapse exotic whitespace to a normal space and trim the result."""
    if not text:
        return ""
    return _ODD_SPACES.sub(" ", text).strip()


def contains_cjk(text: str) -> bool:
    """True when the text contains a meaningful amount of CJK ideographs."""
    if not text:
        return False
    matches = CJK_RE.findall(text)
    return len(matches) >= max(1, len(text) // 200)


# ---------------------------------------------------------------------------
# Anti-bot watermarks (Twkan + common Chinese novel sites)
# ---------------------------------------------------------------------------

WATERMARK_MARKERS = (
    "twkan",
    "台灣小說網",
    "台湾小说网",
    "記住本站",
    "记住本站",
    "本站域名",
    "本站網址",
    "本站网址",
    "全網首發",
    "全网首发",
    "本書由",
    "本书由",
    "google搜索",
    "谷歌搜索",
    "無彈窗",
    "无弹窗",
    "最快更新",
    "章節報錯",
    "章节报错",
    "加入書籤",
    "加入书签",
    "天才一秒",
    "請記住",
    "请记住",
    "最新網址",
    "最新网址",
)

# Watermarks that can be appended after a normal sentence on the same line.
_INLINE_WATERMARKS = re.compile(
    r"(本書由.{0,40}?首發|本书由.{0,40}?首发|【?記住本站.{0,80}?】?|【?记住本站.{0,80}?】?"
    r"|GOOGLE\s*搜索\s*TWKAN|谷歌搜索\s*TWKAN)",
    re.IGNORECASE,
)


def is_watermark_line(line: str) -> bool:
    """Detect a whole line that is an injected anti-bot advertisement."""
    if not line:
        return False
    folded = fold_obfuscated(line).lower()
    return any(marker.lower() in folded for marker in WATERMARK_MARKERS)


def strip_watermark(text: str) -> str:
    """Remove inline watermarks while keeping legitimate prose intact."""
    if not text:
        return ""
    cleaned = _INLINE_WATERMARKS.sub("", fold_obfuscated(text))
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned).strip()
    return cleaned


def sanitize_chapter_text(text: str, paragraph_sep: str = "\n\n") -> str:
    """
    Normalize a chapter body:
      * fold obfuscated Unicode
      * drop empty / watermark-only lines
      * strip inline watermarks
      * collapse the remaining lines into clean paragraphs
    """
    if not text:
        return ""

    paragraphs = []
    for raw_line in text.splitlines():
        line = normalize_spaces(strip_watermark(raw_line))
        if not line:
            continue
        if is_watermark_line(line):
            continue
        paragraphs.append(line)
    return paragraph_sep.join(paragraphs)
