# Multi-Site Novel Scraper (CloakBrowser)

Bộ scraper nhẹ, tốc độ cao, vượt anti-bot bằng CloakBrowser Stealth Chromium. Hỗ trợ **2 nguồn**:

| Nguồn | Domain | Ngôn ngữ | Ghi chú |
|---|---|---|---|
| **SangTacViet** | `14.225.254.182`, `sangtacviet.vip/.app/.com` | Tiếng Việt (convert) | Hỗ trợ tài khoản VIP, mở khóa nguồn Fanqie |
| **Twkan (台灣小說網)** | `twkan.com` | Tiếng Trung phồn thể | Vượt Cloudflare managed challenge, bóc watermark |

Hệ thống cung cấp pipeline kép:
1. **Xuất file Markdown (`.md`):** Đọc truyện tiện lợi, trình bày đẹp mắt.
2. **Xuất file JSONL (`.jsonl`):** Bóc tách phân đoạn tự nhiên, tối ưu cho pipeline tự động làm Video / lồng tiếng AI TTS.
3. **Bộ lọc hậu kỳ (`cleaner.py`):** Tự động tẩy sạch watermark anti-bot (Việt + Trung), chuẩn hóa dấu câu và sửa các lỗi convert tiếng Trung thô.

---

## 🌟 Tính Năng Nổi Bật

1. **Hỗ trợ Tài khoản VIP & Mở khóa nguồn Fanqie (番茄):**
   * Tích hợp chế độ `--login` mở trình duyệt để người dùng đăng nhập VIP trực tiếp 1 lần, tự động lưu session vào `cookies.json`.
   * Tự động replicate cookie xác thực sang mọi domain mirror (`14.225.254.182`, `sangtacviet.vip`, `sangtacviet.app`, `sangtacviet.com`), vượt qua giới hạn 11 chương của nguồn Fanqie/ByteDance.
2. **Kết nối trực tiếp qua IP máy chủ (`http://14.225.254.182/`):**
   * Bỏ qua trung gian Cloudflare, triệt tiêu hoàn toàn lỗi reset kết nối mạng (`ERR_CONNECTION_CLOSED`).
3. **Vượt Anti-bot tầng C++ Binary:**
   * Sử dụng Chromium Stealth của CloakBrowser với 87 bản vá C++, ẩn danh hoàn toàn các dấu hiệu automation (`navigator.webdriver`).
4. **Chặn Resource rác (Route Abortion):**
   * Chặn toàn bộ ảnh, font, media (`.png`, `.jpg`, `.woff2`, `.ttf`, v.v.) và mạng quảng cáo/tracking, tốc độ tải trang cực nhanh (< 0.5s/chương).
5. **Chống rò rỉ bộ nhớ (RAM Recycling):**
   * Tự động tái khởi động `BrowserContext` sau mỗi 50 chương (có thể tùy chỉnh) mà vẫn giữ nguyên cookie VIP.
6. **Bộ lọc hậu kỳ thông minh (`cleaner.py`):**
   * Lọc bỏ watermark `@Bạn đang đọc bản lưu trong hệ thống`.
   * Khắc phục các lỗi dịch máy convert thô (tên nhân vật, danh từ riêng, thuật ngữ trường học, số tiền...).
   * Khử trùng lặp nội dung và sắp xếp chương theo đúng thứ tự thời gian.
7. **Lưu tiến độ liên tục (Checkpointing):**
   * Lưu trạng thái vào `{story_id}_checkpoint.json`, cho phép dừng và tiếp tục cào bất cứ lúc nào.
8. **Hỗ trợ Twkan (台灣小說網) — Cloudflare Managed Challenge:**
   * Tự nhận diện URL `twkan.com/book/{id}/index.html` hoặc `/txt/{id}/{chapter_id}`.
   * Lấy toàn bộ mục lục qua AJAX `/ajax_novels/chapterlist/{id}.html` (không cần cuộn trang).
   * Tự chờ/giải Cloudflare, retry có backoff, nghỉ dài theo burst và recycle context để tránh bị chặn.
   * Bóc sạch watermark Trung văn được làm rối bằng Unicode (`𝕥𝕨𝕜𝕒𝕟.𝕔𝕠𝕞`, `🆃🆆🅺🅰🅽`, `GOOGLE搜索TWKAN`, `全網首發`, ...).
   * Nội dung tiếng Trung được lưu vào `content_zh` với `language="zh"`; `content_vi` để trống (xem mục *Ngôn ngữ đầu ra* bên dưới).

---

## 🚀 Hướng Dẫn Sử Dụng

### 1. Kích hoạt môi trường ảo
```bash
source .venv/bin/activate
pip install -r requirements.txt
```

### 1b. CloakBrowser binary (Linux)

Scraper chỉ dùng **Chromium stealth của CloakBrowser**, không dùng Chromium tải qua Playwright:

* Binary được lưu tại `~/.cloakbrowser/chromium-<version>/chrome` (Linux ELF).
* `config.py` tự tìm bản binary **đúng hệ điều hành hiện tại** (Linux/macOS/Windows) và bỏ qua file `.exe` copy từ máy khác.
* Không cần chạy `playwright install`. Playwright chỉ là lớp điều khiển API mà cloakbrowser dùng.
* Cập nhật bản mới:
  ```bash
  python main.py --update-cloak
  ```
  Nếu server yêu cầu license, lấy **free key** tại link được in ra (hoặc chạy `cloakbrowser login`), sau đó chạy lại lệnh trên. Bản free mới nhất hiện tải được không cần key là Chromium v146; các bản v150+ cần free/Pro key.

### 2. Đăng nhập tài khoản VIP (Chỉ cần làm 1 lần)
```bash
python main.py --login
```
* Trình duyệt sẽ mở trang `https://sangtacviet.vip/`. Bạn đăng nhập tài khoản VIP trên giao diện web.
* Scraper tự nhận diện đăng nhập thành công và lưu toàn bộ cookies vào `cookies.json`.

### 3. Cào truyện (Batch Crawl)

* **Cào thử nghiệm 1 chương (Smoke Test):**
  ```bash
  python main.py -u http://14.225.254.182/truyen/fanqie/1/7392160311094037529/ --smoke-test
  ```

* **Cào batch theo số lượng chương (Ví dụ 250 chương từ chương 1):**
  ```bash
  python main.py -u http://14.225.254.182/truyen/fanqie/1/7392160311094037529/ --start 1 --limit 250 --reset
  ```

* **Cào nối tiếp tiến độ (Ví dụ từ chương 251 đến 500):**
  ```bash
  python main.py -u http://14.225.254.182/truyen/fanqie/1/7392160311094037529/ --start 251 --limit 250
  ```

* **Mở cửa sổ trình duyệt để quan sát (Headed mode):**
  ```bash
  python main.py -u http://14.225.254.182/truyen/fanqie/1/7392160311094037529/ -l 5 --headed
  ```

### 4. Cào truyện từ Twkan (台灣小說網)

Chỉ cần truyền URL truyện hoặc chương của Twkan, scraper tự chọn adapter:

```bash
# Smoke test 1 chương
python main.py -u https://twkan.com/book/97278/index.html --smoke-test

# Cào 100 chương đầu
python main.py -u https://twkan.com/book/97278/index.html --start 1 --limit 100 --reset

# Cào nối tiếp (checkpoint tự động bỏ qua chương đã tải)
python main.py -u https://twkan.com/book/97278/index.html --start 101 --limit 100

# Nếu Cloudflare liên tục chặn, chạy headed để trình duyệt tự giải challenge
python main.py -u https://twkan.com/book/97278/index.html --headed
```

**Lưu ý khi cào Twkan:**
* Mặc định delay **3.5–5.5s/chương**, nghỉ **15s sau mỗi 12 chương**. Đừng giảm delay quá thấp: Cloudflare sẽ trả về trang `Just a moment...`.
* Nếu gặp challenge, scraper chờ tối đa ~35s, reload 1 lần, rồi chờ cooldown và thử lại. Sau 3 lần thất bại, chương đó được bỏ qua và checkpoint vẫn giữ tiến độ để bạn chạy lại sau.
* Cookie Cloudflare được lưu riêng vào `cookies_twkan.json` (không ghi đè `cookies.json` VIP của SangTacViet).
* Có thể đổi tốc độ bằng `--delay 6` hoặc tăng `--recycle 30` nếu máy yếu.

### Ngôn ngữ đầu ra

* **SangTacViet:** văn bản tiếng Việt nằm ở `content_vi` (dùng trực tiếp cho TTS/Video).
* **Twkan:** văn bản gốc tiếng Trung phồn thể nằm ở `content_zh`, `content_vi` để trống, `language="zh"`. File `.md` và `cleaner.py` tự động dùng `content_zh` khi `content_vi` rỗng.
* Muốn chuyển sang giản thể hoặc dịch sang tiếng Việt, hãy chạy thêm bước xử lý ngôn ngữ bên ngoài (hoặc yêu cầu bổ sung module dịch) — scraper chỉ tải và làm sạch nội dung gốc.

---

## 🛠️ Chạy Độc Lập Bộ Lọc Hậu Kỳ (`cleaner.py`)

Nếu bạn đã có sẵn file `.md` hoặc `.jsonl` thô và muốn làm sạch:
```bash
python cleaner.py -i output/7392160311094037529.md
python cleaner.py -i output/7392160311094037529.jsonl
```
Kết quả sạch sẽ được tạo ra tại `output/{story_id}_clean.md` và `output/{story_id}_clean.jsonl`.

---

## 📦 Cấu Trúc File Đầu Ra

* `output/{story_id}.md`: File Markdown thô.
* `output/{story_id}_clean.md`: File Markdown đã lọc sạch watermark, sửa lỗi convert và sắp xếp thứ tự.
* `output/{story_id}_clean.jsonl`: File dữ liệu JSONL phân đoạn đã làm sạch phục vụ TTS/Video.
* `output/{story_id}_checkpoint.json`: File lưu tiến độ cào.
* `cookies.json`: Cookie VIP SangTacViet (do `--login` tạo).
* `cookies_twkan.json`: Cookie Cloudflare của Twkan (tự lưu khi vượt challenge).

---

## 📖 Tài Liệu Nghiên Cứu Chi Tiết

Xem file [LEARNINGS.md](LEARNINGS.md) để tìm hiểu chi tiết về cơ chế reverse engineering, giải mã mã lỗi `4002` của SangTacViet, và cấu trúc hệ thống.
