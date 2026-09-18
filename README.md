# SangTacViet CloakBrowser Scraper

Bộ scraper nhẹ, tốc độ cao, vượt anti-bot C++ binary và hỗ trợ tài khoản VIP để cào dữ liệu truyện từ website `sangtacviet` (thông qua máy chủ trực tiếp `http://14.225.254.182/` hoặc các domain mirror `sangtacviet.vip`, `sangtacviet.app`).

Hệ thống cung cấp pipeline kép:
1. **Xuất file Markdown (`.md`):** Đọc truyện tiện lợi, trình bày đẹp mắt.
2. **Xuất file JSONL (`.jsonl`):** Bóc tách phân đoạn tự nhiên, tối ưu cho pipeline tự động làm Video / lồng tiếng AI TTS.
3. **Bộ lọc hậu kỳ (`cleaner.py`):** Tự động tẩy sạch watermark anti-bot, chuẩn hóa dấu câu và sửa các lỗi convert tiếng Trung thô.

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

---

## 🚀 Hướng Dẫn Sử Dụng

### 1. Kích hoạt môi trường ảo
```bash
source .venv/bin/activate
```

### 2. Đăng nhập tài khoản VIP (Chỉ cần làm 1 lần)
```bash
python main.py --login
```
* Trình duyệt sẽ mở trang `http://14.225.254.182/`. Bạn đăng nhập tài khoản VIP trên giao diện web.
* Sau khi đăng nhập xong, quay lại terminal nhấn `Enter`. Toàn bộ cookies sẽ được lưu tự động vào `cookies.json`.

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

---

## 📖 Tài Liệu Nghiên Cứu Chi Tiết

Xem file [LEARNINGS.md](LEARNINGS.md) để tìm hiểu chi tiết về cơ chế reverse engineering, giải mã mã lỗi `4002` của SangTacViet, và cấu trúc hệ thống.
