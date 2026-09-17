"""
Checkpoint manager for resuming scraper sessions seamlessly.
"""

import json
from pathlib import Path
from typing import Optional, Set
from models import CheckpointData, get_current_iso_time


class CheckpointManager:
    def __init__(self, story_id: str, output_dir: Path):
        self.story_id = story_id
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.checkpoint_path = self.output_dir / f"{story_id}_checkpoint.json"
        
        self.data: CheckpointData = self._load()
        self._completed_set: Set[str] = set(self.data.completed_chapter_ids)

    def _load(self) -> CheckpointData:
        if self.checkpoint_path.exists():
            try:
                with open(self.checkpoint_path, "r", encoding="utf-8") as f:
                    content = json.load(f)
                    return CheckpointData.from_dict(content)
            except Exception:
                pass
        return CheckpointData(story_id=self.story_id)

    def save(self) -> None:
        """Atomically persist checkpoint data to disk."""
        self.data.updated_at = get_current_iso_time()
        self.data.completed_chapter_ids = list(self._completed_set)
        
        temp_path = self.checkpoint_path.with_suffix(".tmp")
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(self.data.to_dict(), f, ensure_ascii=False, indent=2)
        temp_path.replace(self.checkpoint_path)

    def mark_completed(
        self, chapter_id: str, story_title: str = "", next_chapter_id: str = ""
    ) -> None:
        """Record chapter as completed and save checkpoint."""
        self._completed_set.add(chapter_id)
        self.data.last_chapter_id = chapter_id
        if next_chapter_id:
            self.data.next_chapter_id = next_chapter_id
        if story_title and not self.data.story_title:
            self.data.story_title = story_title
        self.save()

    def is_completed(self, chapter_id: str) -> bool:
        """Check if chapter has already been scraped."""
        return chapter_id in self._completed_set

    @property
    def completed_count(self) -> int:
        return len(self._completed_set)

    @property
    def last_chapter_id(self) -> str:
        return self.data.last_chapter_id

    @property
    def next_chapter_id(self) -> str:
        return self.data.next_chapter_id
