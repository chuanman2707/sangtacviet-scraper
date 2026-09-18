"""
Storage layer: Streaming JSONL and human-readable Markdown storage with immediate disk flush.
"""

import json
import os
from pathlib import Path
from models import ChapterRecord


class MarkdownStorage:
    def __init__(self, story_id: str, output_dir: Path):
        self.story_id = story_id
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.file_path = self.output_dir / f"{story_id}.md"

    def append_chapter(self, record: ChapterRecord) -> None:
        """Append chapter formatted in clean readable Markdown (Vietnamese only)."""
        is_new = not self.file_path.exists() or self.file_path.stat().st_size == 0
        with open(self.file_path, "a", encoding="utf-8") as f:
            if is_new:
                f.write(f"# {record.story_title}\n\n")
                f.write(f"- **Mã truyện:** `{record.story_id}`\n")
                f.write(f"- **Nguồn cào:** {record.url}\n\n")
                f.write("---\n\n")

            f.write(f"## {record.chapter_title}\n\n")
            f.write(f"{record.content_vi}\n\n")
            f.write("---\n\n")
            f.flush()
            os.fsync(f.fileno())

    def exists(self) -> bool:
        return self.file_path.exists()

    def reset(self) -> None:
        """Remove file for fresh start."""
        if self.file_path.exists():
            try:
                self.file_path.unlink()
            except Exception:
                pass


class JsonlStorage:
    def __init__(self, story_id: str, output_dir: Path):
        self.story_id = story_id
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.file_path = self.output_dir / f"{story_id}.jsonl"
        self.md_storage = MarkdownStorage(story_id, output_dir)

    def append_chapter(self, record: ChapterRecord) -> None:
        """Append a single chapter record to JSONL and Markdown, immediately flushing to disk."""
        data = record.to_dict()
        if not data.get("content_zh"):
            data.pop("content_zh", None)
        if not data.get("content_hanviet"):
            data.pop("content_hanviet", None)

        line = json.dumps(data, ensure_ascii=False) + "\n"
        with open(self.file_path, "a", encoding="utf-8") as f:
            f.write(line)
            f.flush()
            os.fsync(f.fileno())

        # Also append to Markdown file for easy reading
        self.md_storage.append_chapter(record)

    def exists(self) -> bool:
        return self.file_path.exists()

    def reset(self) -> None:
        """Remove jsonl and md files for fresh start."""
        if self.file_path.exists():
            try:
                self.file_path.unlink()
            except Exception:
                pass
        self.md_storage.reset()

