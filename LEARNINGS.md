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
