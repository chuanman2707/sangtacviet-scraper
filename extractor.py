"""
In-page DOM extractor for SangTacViet chapters.
Extracts aligned bilingual paragraphs (Vietnamese convert, Chinese original, Han-Viet).
"""

from typing import Any, Dict, Optional, Tuple
from playwright.sync_api import Page
from models import ChapterRecord


EXTRACTION_JS = """() => {
    const firstI = document.querySelector("i[t]");
    if (!firstI) return null;
    
    // Container is either class contentbox or parent of i tags
    const container = firstI.closest(".contentbox") || firstI.parentElement;
    
    // Metadata
    const booknameEl = document.getElementById("booknameholder");
    const chapnameEl = document.getElementById("bookchapnameholder");
    const breadcumEl = document.getElementById("breadcum");
    
    let storyTitle = booknameEl ? booknameEl.innerText.trim() : "";
    let chapterTitle = chapnameEl ? chapnameEl.innerText.trim() : "";
    
    if ((!storyTitle || !chapterTitle) && breadcumEl) {
        const parts = breadcumEl.innerText.split("/");
        if (parts.length >= 2) {
            if (!storyTitle) storyTitle = parts[0].trim();
            if (!chapterTitle) chapterTitle = parts.slice(1).join("/").trim();
        }
    }
    
    if (!storyTitle) storyTitle = document.title;
    
    // Build paragraphs for Chinese, Han-Viet, and Vietnamese
    let zhParas = [];
    let hvParas = [];
    
    let curZh = [];
    let curHv = [];
    let consecutiveBrs = 0;
    
    function flushPara() {
        if (curZh.length > 0 || curHv.length > 0) {
            zhParas.push(curZh.join("").trim());
            hvParas.push(curHv.join(" ").trim().replace(/ +/g, " "));
            curZh = [];
            curHv = [];
        }
    }
    
    // Walk through child nodes of container to reconstruct original and Han-Viet
    for (let node of container.childNodes) {
        if (node.nodeType === Node.ELEMENT_NODE) {
            if (node.tagName === "BR") {
                consecutiveBrs++;
                if (consecutiveBrs >= 2) {
                    flushPara();
                }
                continue;
            }
            consecutiveBrs = 0;
            
            if (node.tagName === "I" && node.hasAttribute("t")) {
                const zh = node.getAttribute("t") || "";
                const hv = node.getAttribute("h") || "";
                if (zh) curZh.push(zh);
                if (hv) curHv.push(hv);
            } else if (node.tagName === "SCRIPT" || node.tagName === "STYLE" || node.tagName === "CENTER") {
                continue;
            } else {
                const innerITags = node.querySelectorAll("i[t]");
                if (innerITags.length > 0) {
                    for (let it of innerITags) {
                        const zh = it.getAttribute("t") || "";
                        const hv = it.getAttribute("h") || "";
                        if (zh) curZh.push(zh);
                        if (hv) curHv.push(hv);
                    }
                } else {
                    const text = node.innerText ? node.innerText.trim() : "";
                    if (text) {
                        curZh.push(text);
                        curHv.push(text);
                    }
                }
            }
        } else if (node.nodeType === Node.TEXT_NODE) {
            const val = node.nodeValue ? node.nodeValue.trim() : "";
            if (val) {
                curZh.push(val);
                curHv.push(val);
            }
        }
    }
    flushPara();
    
    // Vietnamese clean text (preserves original natural paragraphs & punctuations)
    const viContent = container.innerText.trim();
    const zhContent = zhParas.join("\\n\\n");
    const hvContent = hvParas.join("\\n\\n");
    
    // Next chapter link
    const nextBtn = document.querySelector("#navnexttop") || document.querySelector("#navnextbot");
    const nextHref = nextBtn ? (nextBtn.getAttribute("href") || "") : "";
    
    return {
        storyTitle,
        chapterTitle,
        viContent,
        zhContent,
        hvContent,
        nextHref,
        tokenCount: document.querySelectorAll("i[t]").length
    };
}"""


def extract_chapter_payload(
    page: Page, story_id: str, chapter_id: str, current_url: str
) -> Tuple[Optional[ChapterRecord], Optional[str]]:
    """
    Executes in-page extraction and returns (ChapterRecord, next_chapter_id).
    """
    data = page.evaluate(EXTRACTION_JS)
    if not data or not data.get("viContent"):
        return None, None

    record = ChapterRecord(
        story_id=story_id,
        story_title=data.get("storyTitle", ""),
        chapter_id=chapter_id,
        chapter_title=data.get("chapterTitle", ""),
        url=current_url,
        content_vi=data.get("viContent", ""),
        content_zh=data.get("zhContent", ""),
        content_hanviet=data.get("hvContent", ""),
    )

    next_href = data.get("nextHref", "")
    next_chapter_id = None
    if next_href:
        # e.g., /truyen/{source}/1/{story_id}/{next_chapter_id}/
        clean = next_href.strip().rstrip("/")
        parts = clean.split("/")
        if len(parts) >= 1:
            candidate = parts[-1]
            if candidate and candidate != "0" and candidate != chapter_id:
                next_chapter_id = candidate

    return record, next_chapter_id
