# SangTacViet Scraper: Kiến Thức Kỹ Thuật & Bài Học Đúc Kết (System Memories)

Tài liệu lưu trữ toàn bộ các phát hiện kỹ thuật, cơ chế hoạt động của SangTacViet, và các cải tiến quan trọng đã được kiểm chứng trong dự án.

---

## 1. Kiến Trúc Mạng & Các Domain Mirror của SangTacViet

* **IP Gốc (Direct Backend Server):** `http://14.225.254.182/`
  * Chạy trên Nginx / Ubuntu, backend engine định danh là `The NG Project 1.1`.
  * **Ưu điểm:** Kết nối trực tiếp qua IP máy chủ giúp bỏ qua hoàn toàn các tầng CDN/Cloudflare trung gian, triệt tiêu lỗi `ERR_CONNECTION_CLOSED` (network reset) thường gặp trên domain `sangtacviet.app`.
* **Cơ chế Fake HTTP 404 (Anti-SEO / Anti-crawler):**
  * Backend SangTacViet chủ động trả về HTTP Header `404 Not Found` cho các trang truyện hợp lệ, nhưng **phần Body HTML lại chứa đầy đủ 100% nội dung truyện**.
  * Các crawler truyền thống (dựa vào `status_code == 200`) sẽ báo lỗi và bỏ qua, trong khi CloakBrowser (dựa trên Playwright/Chromium) vẫn render DOM bình thường.

---

## 2. Bí Ẩn Giới Hạn 11 Chương Của Nguồn Fanqie (番茄小说) & Vòng Lặp Honeypot

* **Nguyên nhân từ Fanqie (ByteDance):**
  * Các bộ truyện nguồn Fanqie (ví dụ: *《都重生了谁还混社会》* - Tác giả *Vô Liêu Tiểu Bạch A*, ID `7392160311094037529`) chỉ mở đọc thử miễn phí công khai trên web từ **Chương 1 đến Chương 11**.
  * Từ **Chương 12 trở đi**, Fanqie khóa web (`isChapterLock: true`, icon `muyeicon-lock`), yêu cầu xác thực tài khoản ByteDance hoặc mở ứng dụng điện thoại. API bị bảo vệ bằng Turing Captcha (`bdturing-verify`).
* **Cơ chế Fallback của SangTacViet (Guest Session):**
  * Khi người dùng ẩn danh (Guest) yêu cầu đọc Chương 12+, server STV gửi request sang Fanqie nhưng bị chặn, nhận về mã lỗi nội bộ:
    ```json
    {"code": "5", "err": "Lỗi không xác định, vui lòng thử lại sau, mã báo lỗi:4002."}
    ```
  * Để trang web không bị crash hoặc trắng xóa, STV tự động fallback/redirect về nạp lại các chương đã lưu sẵn trong cache (`@Bạn đang đọc bản lưu trong hệ thống` - chính là 11 chương đầu).
  * **Hậu quả nếu không có VIP:** Dù crawler chạy qua 250 lượt CID khác nhau, nội dung trả về thực tế chỉ là 11 chương đầu lặp đi lặp lại.

---

## 3. Cơ Chế Xác Thực Tài Khoản VIP & Tái Lập Cookie Đa Miền

* **Các Cookie Xác Thực Trọng Yếu:**
  * `useri2`: Token định danh tài khoản người dùng STV.
  * `access`: Quyền hạn truy cập và cấp độ VIP.
  * `PHPSESSID`: Phiên làm việc PHP session.
  * `_acx`, `arouting`: Token định tuyến máy chủ nội bộ.
* **Kỹ Thuật Replicate Cookie Cho IP & Domain (Playwright):**
  * Playwright từ chối thuộc tính `domain` đối với địa chỉ IP thuần (`14.225.254.182`) nếu có dấu chấm phía trước.
  * **Giải pháp chuẩn:** Khi nạp cookie vào `BrowserContext`, sử dụng tham số `url` thay vì `domain`:
    ```python
    context.add_cookies([
        {"name": name, "value": val, "url": f"http://14.225.254.182"},
        {"name": name, "value": val, "url": f"https://sangtacviet.vip"},
        {"name": name, "value": val, "url": f"https://sangtacviet.app"},
        {"name": name, "value": val, "url": f"https://sangtacviet.com"},
    ])
    ```
  * Việc replicate cookie sang toàn bộ các mirror domain giúp bot chuyển hướng giữa IP và domain mà không bao giờ bị rớt phiên đăng nhập VIP.
* **Tính Năng `--login` Tự Động:**
  * Hỗ trợ cờ `--login` mở trình duyệt Chromium thực tế để người dùng đăng nhập trực quan 1 lần. Toàn bộ session được kết xuất tự động ra file `cookies.json` để dùng vĩnh viễn cho các lần cào sau.

---

## 4. Tối Ưu Hóa Hiệu Năng & Tránh Bị Phát Hiện

* **CloakBrowser C++ Binary Patches:**
  * Tận dụng bản build Chromium tùy biến với 87 bản vá C++ ẩn danh (xóa sạch dấu vết `navigator.webdriver`, `chrome.runtime`, fingerprinting).
* **Route Abortion (Chặn Tài Nguyên Nặng):**
  * Chặn tải toàn bộ ảnh (`.png`, `.jpg`, `.webp`), font chữ (`.woff2`, `.ttf`), media (`.mp3`, `.mp4`) và các script theo dõi (Google Analytics, Facebook Pixel), giảm thời gian tải trang xuống **< 0.5s / chương**.
* **Chống Tràn RAM (Context Recycling):**
  * Cứ sau 50 chương, tự động làm mới `BrowserContext` trong khi vẫn bảo lưu toàn bộ cookies của phiên hiện tại, giữ mức tiêu thụ RAM luôn ổn định dưới 200MB cho dù cào hàng ngàn chương liên tục.

---

## 5. Pipeline Xử Lý Hậu Kỳ Văn Bản (`cleaner.py`)

* **Lọc Watermark Anti-Bot:**
  * Quét và loại bỏ các dòng chèn tự động của SangTacViet: `@Bạn đang đọc bản lưu trong hệ thống`, `@...`, các tên miền quảng cáo.
* **Sửa Lỗi Dịch Thô (Convert Polish Glossary):**
  * Khắc phục các lỗi dịch máy ngô nghê điển hình:
    * *"Quan thượng tá đích tôn môn"* -> *"Đóng cửa phòng hiệu trưởng lại"*
    * *"Bỉ so sánh"* -> *"Khá là"*
    * *"Khán trứ"* -> *"Chăm chú nhìn"* / *"Nhìn"*
    * Tên riêng nhân vật: *"Trắng lộ"* -> *"Bạch Lộ"*, *"Vệ bão tố"* -> *"Vệ Bão Tố"*, *"Bốn chín"* -> *"Tứ Cửu"*.
* **Làm Mượt Đoạn Văn (Paragraph Smoothing):**
  * Nối các câu/từ đơn lẻ bị ngắt dòng bất thường mà vẫn bảo vệ các khối lời thoại (`"..."`, `“...”`) và danh từ riêng.
* **Khử Trùng Lặp & Sắp Xếp Trình Tự:**
  * Deduplicate dựa trên nội dung đã làm sạch và sắp xếp chương theo đúng thứ tự thời gian tăng dần.

---

## 6. Định Dạng Xuất Đa Mục Tiêu

1. **`.md` (Markdown):** Được cấu trúc theo tiêu đề chuẩn `# Tên Truyện` và `## Thứ N chương ...`, tiện lợi cho việc đọc trực tiếp trên máy tính hoặc điện thoại.
2. **`.jsonl` (JSON Lines):** Mỗi dòng là một bản ghi JSON độc lập gồm nội dung tiếng Việt (`content_vi`), tiếng Trung gốc (`content_zh`), âm Hán Việt (`content_hanviet`), tối ưu cho pipeline tự động sinh video YouTube / TikTok và đọc lồng tiếng bằng AI TTS.

---

## 7. Twkan (台灣小說網) — Cloudflare Managed Challenge & Cấu Trúc Trang

### 7.1. Kiến trúc URL & dữ liệu

* **Book page:** `https://twkan.com/book/{book_id}.html`
* **Chapter index:** `https://twkan.com/book/{book_id}/index.html`
* **Chapter list API:** `https://twkan.com/ajax_novels/chapterlist/{book_id}.html`
  * Trả về fragment `<ul><li data-num="N"><a href="...">Tên chương</a></li>...</ul>`.
  * `data-num` là **thứ tự** (1..N), không phải số chương trong tiêu đề (tiêu đề có thể nhảy số do truyện bị xóa chương).
  * `href` là URL tuyệt đối dạng `https://twkan.com/txt/{book_id}/{chapter_id}`.
* **Chapter page:** `https://twkan.com/txt/{book_id}/{chapter_id}`
  * Nội dung nằm trong `div#txtcontent0` (text + `<br>`, không phải JSON/JS mã hóa).
  * Tiêu đề chương: `div.txtnav h1`; metadata truyện: `window.bookinfo.articlename` / `author`.
  * Link chương kế: `div.page1 a` có text `下一章` (không có `#pb_next`).
* **Không có phân trang nội dung**: mỗi chương là 1 trang duy nhất.

### 7.2. Cloudflare & phòng chống crawl

* Site dùng **Cloudflare Managed Challenge** (`cType: 'managed'`). Khi bị nghi ngờ, server trả trang `Just a moment...` với HTTP 403; body không có nội dung truyện.
* Challenge xuất hiện **ngẫu nhiên theo burst**, không phải mọi request. Trong test: ~1/15 request với delay 1.5s; giảm xuống gần như 0 khi delay 3.5–5.5s và nghỉ 15s mỗi 12 chương.
* CloakBrowser (Chromium C++ patches) render được trang twkan ở **headless**; headed + `humanize=True` giúp giảm tần suất challenge.
* Chiến lược trong code:
  1. Phát hiện challenge qua title/DOM (`page_is_challenge`).
  2. Chờ tối đa ~35s, thử click Turnstile checkbox, reload 1 lần.
  3. Nếu vẫn chặn: chờ cooldown 20s, recycle `BrowserContext` (giữ cookie), thử lại tối đa 3 lần.
  4. Thất bại thì bỏ qua chương (không đánh dấu checkpoint) để lần chạy sau tải lại.

### 7.3. Watermark & làm sạch

* Watermark được chèn ngẫu nhiên vào nội dung, làm rối bằng Unicode:
  * `本書由𝕥𝕨𝕜𝕒𝕟.𝕔𝕠𝕞全網首發` (Mathematical Alphanumeric Symbols).
  * `【記住本站域名 ... 🆃🆆🅺🅰🅽.🅲🅾🅼超實用 】` (Squared Alphanumerics).
  * `GOOGLE搜索TWKAN`.
* `textnorm.py` chuẩn hóa các ký tự obfuscated về ASCII trước khi so khớp, sau đó `sanitize_chapter_text()` loại bỏ cả dòng watermark và watermark inline.
* Nội dung tiếng Trung được giữ nguyên đoạn văn; **không** chạy các rule sửa lỗi convert tiếng Việt và không merge dòng ngắn (sẽ làm hỏng văn phong Trung).

### 7.4. Lưu trữ & ngôn ngữ

* `ChapterRecord` có thêm `source` và `language`; Twkan ghi `content_zh`, `language="zh"`, `content_vi=""`.
* `storage.py` dùng `record.body` (= `content_vi or content_zh`) cho file Markdown.
* `cleaner.py` tự chọn `content_vi` nếu có, ngược lại làm sạch `content_zh`; `parse_chapter_number()` hiểu cả `第12章` và `Chương 12`.

---

## 8. CloakBrowser trên Linux (không dùng Chromium của Playwright)

* Dự án chỉ dùng đúng một loại browser: **CloakBrowser stealth Chromium**. Nhánh fallback `sync_playwright().chromium.launch(...)` đã bị loại bỏ.
* Playwright vẫn là dependency vì `cloakbrowser` dùng API Playwright để điều khiển binary, nhưng **không** dùng browser do `playwright install` tải về.
* Binary hợp lệ nằm ở:
  * Linux: `~/.cloakbrowser/chromium-<version>/chrome`
  * macOS: `~/.cloakbrowser/chromium-<version>/Chromium.app/Contents/MacOS/Chromium`
  * Windows: `~/.cloakbrowser/chromium-<version>/chrome.exe`
* `config.find_cached_cloak_binary()` chỉ chấp nhận file thực thi đúng platform hiện tại, nên binary `.exe` copy từ Windows sẽ bị bỏ qua trên Linux.
* Thứ tự ưu tiên khi resolve binary:
  1. `CLOAKBROWSER_BINARY_PATH` (nếu file tồn tại).
  2. Binary cache mới nhất trong `~/.cloakbrowser` (không cần license, không hỏi key).
  3. `cloakbrowser.download.ensure_binary()` (bản latest có thể cần free/Pro key).
* Cập nhật binary: `python main.py --update-cloak`. Nếu bị hỏi key, lấy free key qua link hoặc `cloakbrowser login`.
* Giới hạn phiên bản: cloakbrowser `0.7.3` chạy tốt với Playwright `1.65.x`; cloakbrowser `0.6.x` sẽ lỗi import với Playwright `1.65` (module `playwright._impl._js_handle` đã đổi).
