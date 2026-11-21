#!/usr/bin/env python3
"""
CLI Runner for SangTacViet CloakBrowser Scraper.
Produces high-quality bilingual novel text formatted for video generation / TTS.
"""

import argparse
import sys
if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from config import DEFAULT_OUTPUT_DIR, DEFAULT_RECYCLE_EVERY
from models import ChapterRecord
from scraper import NovelScraper

console = Console()


def render_banner():
    banner_text = (
        "[bold cyan]Multi-Site Novel Scraper (CloakBrowser)[/bold cyan]\n"
        "[dim]SangTacViet (VIP/convert) + Twkan (台灣小說網) — vượt Cloudflare, "
        "xuất Markdown / JSONL cho Video & TTS[/dim]"
    )
    console.print(Panel(banner_text, expand=False, border_style="cyan"))


def on_chapter_progress(record: ChapterRecord, index: int, total: int = 0):
    total_str = f"/{total}" if total else ""
    body = record.body or ""
    snippet = body[:120].replace("\n", " ") + "..."
    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_row(
        "[bold green]✓[/bold green]",
        f"[bold cyan][{index}{total_str}][/bold cyan] [bold]{record.chapter_title}[/bold] [dim](ID: {record.chapter_id})[/dim]"
    )
    table.add_row("", f"[dim]Preview: {snippet}[/dim]")
    console.print(table)


def main():
    parser = argparse.ArgumentParser(
        description="Cào dữ liệu truyện từ SangTacViet hoặc Twkan bằng CloakBrowser Stealth Chromium"
    )
    parser.add_argument(
        "--url",
        "-u",
        default="http://14.225.254.182/truyen/fanqie/1/7392160311094037529/",
        help=(
            "URL truyện hoặc chương. Ví dụ: "
            "http://14.225.254.182/truyen/fanqie/1/7392160311094037529/ "
            "hoặc https://twkan.com/book/97278/index.html"
        ),
    )
    parser.add_argument(
        "--login",
        action="store_true",
        help="Mở trình duyệt để đăng nhập tài khoản VIP SangTacViet và lưu cookie tự động",
    )
    parser.add_argument(
        "--update-cloak",
        action="store_true",
        help="Cập nhật/tải bản CloakBrowser Linux mới nhất (có thể yêu cầu free key)",
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
        "--delay",
        "-d",
        type=float,
        default=None,
        help="Thời gian chờ giữa các chương (giây). Mặc định: SangTacViet 10s, Twkan 3.5–5.5s",
    )
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="Cào thử nghiệm đúng 1 chương đầu tiên và in chi tiết mẫu dữ liệu",
    )

    args = parser.parse_args()

    render_banner()

    limit = 1 if args.smoke_test else args.limit

    if args.update_cloak:
        import os
        from cloakbrowser.download import ensure_binary

        console.print("\n[bold cyan]=== CẬP NHẬT CLOAKBROWSER ===")
        console.print("[dim]Đang kiểm tra bản Chromium stealth mới nhất cho Linux...[/dim]")
        # Bỏ override để downloader lấy bản mới thay vì dùng cache cũ.
        os.environ.pop("CLOAKBROWSER_BINARY_PATH", None)
        try:
            path = ensure_binary()
            console.print(f"[bold green]✓ CloakBrowser binary:[/bold green] {path}")
            try:
                from cloakbrowser import binary_info
                info = binary_info()
                console.print(
                    f"[dim]Phiên bản: {info.get('version')} | "
                    f"Platform: {info.get('platform')}[/dim]"
                )
            except Exception:
                pass
        except Exception as e:
            console.print(f"[yellow]Không tải được bản mới: {e}[/yellow]")
            console.print(
                "[dim]Nếu cần free key, chạy: cloakbrowser login "
                "(hoặc đặt CLOAKBROWSER_LICENSE_KEY).[/dim]"
            )
        return

    if args.login:
        from browser_manager import BrowserManager
        import time
        login_url = "https://sangtacviet.vip/"
        console.print("\n[bold cyan]=== ĐĂNG NHẬP SANGTACVIET (VIP) ===[/bold cyan]")
        console.print(f"[dim]Mục tiêu:[/dim] {login_url}")
        console.print("[dim]Đang mở cửa sổ trình duyệt Chromium...[/dim]\n")
        
        bm = BrowserManager(headless=False, target_url=login_url)
        page = bm.start()
        page.goto(login_url, wait_until="domcontentloaded")
        
        try:
            page.evaluate("""() => {
                if (window.openloginmodal) window.openloginmodal();
                setTimeout(() => {
                    const u = document.querySelector('input[name="user"]') || document.querySelector('#login input[type="text"]');
                    if (u && !u.value) u.value = 'Xong Con Bê';
                }, 300);
            }""")
        except Exception:
            pass

        console.print("[bold yellow]Vui lòng nhập mật khẩu và bấm 'Đăng nhập' trên cửa sổ trình duyệt.[/bold yellow]")
        console.print("[dim]Hệ thống đang TỰ ĐỘNG nhận diện khi đăng nhập thành công để lưu cookies...[/dim]\n")
        
        logged_in = False
        start_wait = time.time()
        while time.time() - start_wait < 300:
            time.sleep(1.0)
            try:
                cookies = bm._context.cookies()
                c_names = {c["name"] for c in cookies}
                if "useri2" in c_names or "access" in c_names:
                    logged_in = True
                    break
                is_auth = page.evaluate("""() => {
                    const el = document.getElementById('tm-nav-search-top-right');
                    return el && !el.innerText.includes('Đăng nhập');
                }""")
                if is_auth:
                    logged_in = True
                    break
            except Exception:
                break
        
        time.sleep(1.0)
        count = bm.save_cookies("cookies.json")
        bm.close()
        if logged_in:
            console.print(f"\n[bold green]✓ Đã phát hiện đăng nhập thành công! Đã lưu {count} cookies vào cookies.json![/bold green]")
        else:
            console.print(f"\n[bold green]✓ Đã lưu {count} cookies vào cookies.json![/bold green]")
        console.print("[dim]Bây giờ bạn có thể bắt đầu cào truyện với tài khoản VIP đã xác thực.[/dim]\n")
        return

    try:
        scraper = NovelScraper(
            target_url=args.url,
            max_chapters=limit,
            start_index=args.start,
            reset=args.reset,
            headless=not args.headed,
            output_dir=args.output_dir,
            recycle_every=args.recycle,
            cookie_source=args.cookie,
            on_chapter_crawled=on_chapter_progress,
            delay=args.delay,
        )

        mode_str = "[yellow]SMOKE TEST (1 chương)[/yellow]" if args.smoke_test else f"[green]{limit or 'Hết truyện'} chương (bắt đầu từ #{args.start})[/green]"
        console.print(f"[bold]Mục tiêu:[/bold] {args.url}")
        console.print(f"[bold]Nguồn:[/bold] {scraper.adapter.display_name}")
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
                # Chinese sources keep their original paragraph flow: the
                # Vietnamese "merge short lines" heuristic would damage them.
                is_zh = scraper.adapter.name == "twkan"
                cleaner = NovelCleaner(remove_emoticons=False, merge_short_lines=not is_zh)
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
                    body_vi = last_obj.get('content_vi', '')
                    body_zh = last_obj.get('content_zh', '')
                    if body_vi:
                        body_panel = (
                            f"[bold green]Nội dung Tiếng Việt (Kịch bản TTS / Video):[/bold green]\n"
                            f"{body_vi[:300]}...\n\n"
                            f"[bold yellow]Nội dung Tiếng Trung gốc:[/bold yellow]\n"
                            f"{body_zh[:150]}..."
                        )
                    else:
                        body_panel = (
                            f"[bold green]Nội dung gốc (Tiếng Trung):[/bold green]\n"
                            f"{body_zh[:400]}..."
                        )
                    sample_panel = (
                        f"[bold cyan]Truyện:[/bold cyan] {last_obj.get('story_title')}\n"
                        f"[bold cyan]Chương:[/bold cyan] {last_obj.get('chapter_title')} (ID: {last_obj.get('chapter_id')})\n"
                        f"[bold cyan]Nguồn / Ngôn ngữ:[/bold cyan] {last_obj.get('source', '')} / {last_obj.get('language', 'vi')}\n\n"
                        f"{body_panel}"
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
