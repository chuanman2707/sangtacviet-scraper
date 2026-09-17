#!/usr/bin/env python3
"""
CLI Runner for SangTacViet CloakBrowser Scraper.
Produces high-quality bilingual novel text formatted for video generation / TTS.
"""

import argparse
import sys
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from config import DEFAULT_OUTPUT_DIR, DEFAULT_RECYCLE_EVERY
from models import ChapterRecord
from scraper import SangTacVietScraper

console = Console()


def render_banner():
    banner_text = (
        "[bold cyan]SangTacViet CloakBrowser Scraper[/bold cyan]\n"
        "[dim]Cào truyện tốc độ cao, vượt anti-bot C++ binary, trích xuất text phục vụ làm Video / TTS[/dim]"
    )
    console.print(Panel(banner_text, expand=False, border_style="cyan"))


def on_chapter_progress(record: ChapterRecord, index: int):
    vi_snippet = record.content_vi[:120].replace("\n", " ") + "..."
    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_row("[bold green]✓[/bold green]", f"[bold]Chương {record.chapter_id}[/bold]: {record.chapter_title}")
    table.add_row("", f"[dim]Preview Vi: {vi_snippet}[/dim]")
    console.print(table)


def main():
    parser = argparse.ArgumentParser(
        description="Cào dữ liệu truyện từ SangTacViet bằng CloakBrowser Stealth Chromium"
    )
    parser.add_argument(
        "--url",
        "-u",
        required=True,
        help="URL truyện hoặc chương (vd: https://sangtacviet.app/truyen/dich/1/53028/)",
    )
    parser.add_argument(
        "--limit",
        "-l",
        type=int,
        default=None,
        help="Số lượng chương tối đa cần cào (mặc định: cào hết)",
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Mở cửa sổ Chromium thực tế để quan sát (mặc định chạy ngầm headless)",
    )
    parser.add_argument(
        "--output-dir",
        "-o",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Thư mục lưu file JSONL (mặc định: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--recycle",
        type=int,
        default=DEFAULT_RECYCLE_EVERY,
        help=f"Số chương mỗi lần restart BrowserContext chống rò rỉ RAM (mặc định: {DEFAULT_RECYCLE_EVERY})",
    )
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="Cào thử nghiệm đúng 1 chương đầu tiên và in chi tiết mẫu dữ liệu",
    )

    args = parser.parse_args()

    render_banner()

    limit = 1 if args.smoke_test else args.limit

    try:
        scraper = SangTacVietScraper(
            target_url=args.url,
            max_chapters=limit,
            headless=not args.headed,
            output_dir=args.output_dir,
            recycle_every=args.recycle,
            on_chapter_crawled=on_chapter_progress,
        )

        mode_str = "[yellow]SMOKE TEST (1 chương)[/yellow]" if args.smoke_test else f"[green]{limit or 'Hết truyện'} chương[/green]"
        console.print(f"[bold]Mục tiêu:[/bold] {args.url}")
        console.print(f"[bold]Chế độ:[/bold] {mode_str} | [bold]Hiển thị:[/bold] {'Headed' if args.headed else 'Headless'}")
        console.print(f"[bold]Thư mục xuất:[/bold] {args.output_dir.resolve()}\n")

        with console.status("[cyan]Đang khởi động CloakBrowser & xử lý truyện...[/cyan]"):
            total = scraper.run()

        console.print(f"\n[bold green]Hoàn thành![/bold green] Đã lưu {total} chương vào file JSONL.")
        output_file = args.output_dir / f"{scraper.story_id}.jsonl"
        checkpoint_file = args.output_dir / f"{scraper.story_id}_checkpoint.json"

        if output_file.exists():
            console.print(f"[bold]File dữ liệu:[/bold] [underline]{output_file}[/underline]")
        if checkpoint_file.exists():
            console.print(f"[bold]File checkpoint:[/bold] [underline]{checkpoint_file}[/underline]")

        if args.smoke_test and output_file.exists():
            # In mẫu dữ liệu chi tiết cho người dùng
            import json
            with open(output_file, "r", encoding="utf-8") as f:
                lines = f.readlines()
                if lines:
                    last_obj = json.loads(lines[-1])
                    sample_panel = (
                        f"[bold cyan]Truyện:[/bold cyan] {last_obj.get('story_title')}\n"
                        f"[bold cyan]Chương:[/bold cyan] {last_obj.get('chapter_title')} (ID: {last_obj.get('chapter_id')})\n\n"
                        f"[bold green]Nội dung Tiếng Việt (Kịch bản TTS / Video):[/bold green]\n"
                        f"{last_obj.get('content_vi', '')[:300]}...\n\n"
                        f"[bold yellow]Nội dung Tiếng Trung gốc:[/bold yellow]\n"
                        f"{last_obj.get('content_zh', '')[:150]}...\n\n"
                        f"[bold magenta]Âm Hán Việt tương ứng:[/bold magenta]\n"
                        f"{last_obj.get('content_hanviet', '')[:150]}..."
                    )
                    console.print("\n", Panel(sample_panel, title="Chi Tiết Dữ Liệu Chương Cào Được", border_style="green"))

    except KeyboardInterrupt:
        console.print("\n[yellow]Đã tạm dừng scraper. Tiến độ đã được lưu trong checkpoint.[/yellow]")
        sys.exit(0)
    except Exception as e:
        console.print(f"\n[bold red]Lỗi:[/bold red] {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
