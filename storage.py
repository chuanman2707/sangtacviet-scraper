"""
Streaming JSONL storage with immediate disk flush.
"""

import json
import os
from pathlib import Path
from models import ChapterRecord


class JsonlStorage:
    def __init__(self, story_id: str, output_dir: Path):
        self.story_id = story_id
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.file_path = self.output_dir / f"{story_id}.jsonl"

    def append_chapter(self, record: ChapterRecord) -> None:
        """Append a single chapter record to JSONL and immediately flush to disk."""
        line = json.dumps(record.to_dict(), ensure_ascii=False) + "\n"
        with open(self.file_path, "a", encoding="utf-8") as f:
            f.write(line)
            f.flush()
            os.fsync(f.fileno())

    def exists(self) -> bool:
        return self.file_path.exists()
