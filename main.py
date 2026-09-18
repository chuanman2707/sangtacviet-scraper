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


def on_chapter_progress(record: ChapterRecord, index: int, total: int = 0):
    total_str = f"/{total}" if total else ""
    vi_snippet = record.content_vi[:120].replace("\n", " ") + "..."
    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_row(
        "[bold green]✓[/bold green]",
        f"[bold cyan][{index}{total_str}][/bold cyan] [bold]{record.chapter_title}[/bold] [dim](ID: {record.chapter_id})[/dim]"
    )
    table.add_row("", f"[dim]Preview: {vi_snippet}[/dim]")
    console.print(table)


def main():
    parser = argparse.ArgumentParser(
        description="Cào dữ liệu truyện từ SangTacViet bằng CloakBrowser Stealth Chromium"
    )
    parser.add_argument(
        "--url",
        "-u",
        default="http://14.225.254.182/truyen/fanqie/1/7392160311094037529/",
        help="URL truyện hoặc chương (vd: http://14.225.254.182/truyen/fanqie/1/7392160311094037529/)",
    )
    parser.add_argument(
        "--login",
        action="store_true",
        help="Mở trình duyệt trực tiếp để đăng nhập tài khoản VIP vào SangTacViet và lưu cookie tự động",
    )
    parser.add_argument(
        "--cookie",
        "-c",
        default=None,
        help="Đường dẫn file cookie (cookies.json / cookies.txt) hoặc chuỗi raw cookie",
    )
    parser.add_argument(
        "--start",
        "-s",
        type=int,
        default=1,
        help="Số thứ tự chương bắt đầu cào (1-based, mặc định: 1)",
    )
    parser.add_argument(
        "--limit",
        "-l",
        type=int,
        default=None,
        help="Số lượng chương tối đa cần cào (mặc định: cào hết)",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Xóa checkpoint và file cũ để cào mới từ đầu",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        default=True,
        help="Tự động chạy bộ lọc cleaner.py hậu kỳ sau khi cào xong (mặc định: Bật)",
    )
    parser.add_argument(
        "--no-clean",
        action="store_false",
        dest="clean",
        help="Tắt tự động chạy bộ lọc cleaner.py",
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

    if args.login:
        from browser_manager import BrowserManager
        login_url = args.url if "/truyen/" not in args.url else "http://14.225.254.182/"
        console.print(f"\n[bold cyan]=== ĐĂNG NHẬP SANGTACVIET (VIP) ===[/bold cyan]")
        console.print(f"[dim]Mục tiêu:[/dim] {login_url}")
        console.print("[dim]Đang mở cửa sổ trình duyệt Chromium...[/dim]\n")
        
        bm = BrowserManager(headless=False, target_url=login_url)
        page = bm.start()
        page.goto(login_url, wait_until="domcontentloaded")
        
        try:
            page.evaluate("() => window.openloginmodal && window.openloginmodal()")
        except Exception:
            pass

        console.print("[bold yellow]Vui lòng đăng nhập tài khoản VIP trên cửa sổ trình duyệt vừa mở.[/bold yellow]")
        console.print("[dim]Sau khi đăng nhập xong, quay lại cửa sổ terminal này và nhấn [ENTER] để lưu cookies...[/dim]\n")
        
        input("Nhấn [ENTER] sau khi đã đăng nhập thành công: ")
        
        count = bm.save_cookies("cookies.json")
        bm.close()
        console.print(f"\n[bold green]✓ Đã lưu thành công {count} cookies vào cookies.json![/bold green]")
        console.print("[dim]Bây giờ bạn có thể bắt đầu cào truyện với tài khoản VIP đã xác thực.[/dim]\n")
        return

    try:
        scraper = SangTacVietScraper(
            target_url=args.url,
            max_chapters=limit,
            start_index=args.start,
            reset=args.reset,
            headless=not args.headed,
            output_dir=args.output_dir,
            recycle_every=args.recycle,
            cookie_source=args.cookie,
            on_chapter_crawled=on_chapter_progress,
        )

        mode_str = "[yellow]SMOKE TEST (1 chương)[/yellow]" if args.smoke_test else f"[green]{limit or 'Hết truyện'} chương (bắt đầu từ #{args.start})[/green]"
        console.print(f"[bold]Mục tiêu:[/bold] {args.url}")
        console.print(f"[bold]Chế độ:[/bold] {mode_str} | [bold]Hiển thị:[/bold] {'Headed' if args.headed else 'Headless'}")
        console.print(f"[bold]Thư mục xuất:[/bold] {args.output_dir.resolve()}\n")

        with console.status("[cyan]Đang khởi động CloakBrowser & xử lý truyện...[/cyan]"):
            total = scraper.run()

        console.print(f"\n[bold green]Hoàn thành cào truyện![/bold green] Đã lưu {total} chương.")
        output_file = args.output_dir / f"{scraper.story_id}.jsonl"
        output_md = args.output_dir / f"{scraper.story_id}.md"
        checkpoint_file = args.output_dir / f"{scraper.story_id}_checkpoint.json"

        if output_file.exists():
            console.print(f"[bold]File dữ liệu JSONL:[/bold] [underline]{output_file}[/underline]")
        if output_md.exists():
            console.print(f"[bold]File đọc Markdown (.md):[/bold] [underline]{output_md}[/underline]")
        if checkpoint_file.exists():
            console.print(f"[bold]File checkpoint:[/bold] [underline]{checkpoint_file}[/underline]")

        # Hậu kỳ làm sạch văn bản nếu bật clean
        if args.clean and output_md.exists():
            console.print("\n[cyan]Đang thực hiện hậu kỳ làm sạch văn bản bằng cleaner.py...[/cyan]")
            try:
                from cleaner import NovelCleaner, clean_markdown_file, clean_jsonl_file
                cleaner = NovelCleaner(remove_emoticons=False, merge_short_lines=True)
                clean_md = args.output_dir / f"{scraper.story_id}_clean.md"
                clean_jsonl = args.output_dir / f"{scraper.story_id}_clean.jsonl"
                stats_md = clean_markdown_file(output_md, clean_md, cleaner)
                if output_file.exists():
                    clean_jsonl_file(output_file, clean_jsonl, cleaner)
                console.print(f"[bold green]✓ Hậu kỳ hoàn tất![/bold green] Đã xử lý {stats_md.get('unique', 0)} chương.")
                console.print(f"[bold]File Markdown sạch:[/bold] [underline]{clean_md}[/underline]")
                console.print(f"[bold]File JSONL sạch:[/bold] [underline]{clean_jsonl}[/underline]")
            except Exception as e:
                console.print(f"[yellow]Lỗi khi chạy cleaner.py hậu kỳ: {e}[/yellow]")

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
