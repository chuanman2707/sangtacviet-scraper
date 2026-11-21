"""
Data models for SangTacViet Scraper.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List


def get_current_iso_time() -> str:
    """Return current UTC time in ISO format."""
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ChapterRecord:
    """
    Clean chapter record formatted specifically for AI video narration & TTS.

    ``content_vi`` holds Vietnamese text when the source provides it
    (SangTacViet).  Chinese-only sources (Twkan) fill ``content_zh`` instead and
    set ``language="zh"``; storage and the CLI fall back to whichever field is
    populated.
    """
    story_id: str
    story_title: str
    chapter_id: str
    chapter_title: str
    url: str
    content_vi: str
    content_zh: str = ""
    content_hanviet: str = ""
    source: str = ""
    language: str = "vi"
    crawled_at: str = field(default_factory=get_current_iso_time)

    @property
    def body(self) -> str:
        """Best available text body (Vietnamese first, then Chinese)."""
        return self.content_vi or self.content_zh

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CheckpointData:
    """State of crawling progress for a specific story."""
    story_id: str
    story_title: str = ""
    last_chapter_id: str = ""
    next_chapter_id: str = ""
    completed_chapter_ids: List[str] = field(default_factory=list)
    updated_at: str = field(default_factory=get_current_iso_time)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CheckpointData":
        return cls(
            story_id=data.get("story_id", ""),
            story_title=data.get("story_title", ""),
            last_chapter_id=data.get("last_chapter_id", ""),
            next_chapter_id=data.get("next_chapter_id", ""),
            completed_chapter_ids=data.get("completed_chapter_ids", []),
            updated_at=data.get("updated_at", get_current_iso_time()),
        )
