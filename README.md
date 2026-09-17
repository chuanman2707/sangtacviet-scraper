# SangTacViet CloakBrowser Scraper

Bộ scraper nhẹ, tốc độ cao để cào dữ liệu truyện từ website `sangtacviet.app` (và các mirror domain) bằng **CloakBrowser Stealth Chromium binary**.
Dữ liệu được bóc tách và phân đoạn văn bản tự nhiên, tối ưu đặc biệt cho **pipeline làm Video / lồng tiếng TTS / lưu trữ truyện**.

---

## 🌟 Tính Năng Nổi Bật
1. **Không phụ thuộc Docker:** Chạy trực tiếp qua Python script, tiết kiệm RAM và dung lượng đĩa.
2. **Vượt Anti-bot tầng C++ Binary:** Sử dụng Chromium Stealth của CloakBrowser với 87 bản vá C++, vượt qua cơ chế anti-bot và cookie obfuscation (`_ac`, `_gac`, `_acx`) của SangTacViet.
3. **Chặn Resource rác (Route Abortion):** Tự động chặn toàn bộ request tải ảnh, font, media (`.png`, `.jpg`, `.woff2`, `.ttf`, v.v.) và mạng quảng cáo/tracking, giúp tải trang cực nhanh (dưới 1s/chương).
4. **Chống rò rỉ bộ nhớ (Anti-leak RAM):** Tự động tái khởi động `BrowserContext` sau mỗi 50 chương (có thể tùy chỉnh) mà vẫn bảo lưu cookies, giữ RAM luôn ổn định khi cào hàng ngàn chương.
5. **Streaming Append & Checkpoint:** Dữ liệu mỗi chương cào xong được ghi ngay lập tức (kèm `flush()` và `os.fsync()`) vào `output/{story_id}.jsonl`. Tự động ghi nhớ tiến độ vào `{story_id}_checkpoint.json` để tiếp tục bất cứ lúc nào khi bị gián đoạn.
6. **Văn bản phân đoạn tự nhiên:** Bóc tách đồng thời cả 3 định dạng: Tiếng Việt convert (`content_vi`), Tiếng Trung gốc (`content_zh`), và Âm Hán Việt (`content_hanviet`), giữ trọn ngắt dòng `\n\n` phục vụ kịch bản video.

---

## 🚀 Hướng Dẫn Sử Dụng

### 1. Kích hoạt môi trường ảo
```bash
cd /Users/binhan/.gemini/antigravity/scratch/stv-cloak-scraper
source .venv/bin/activate
```

### 2. Chạy thử nghiệm 1 chương (Smoke Test)
```bash
python main.py -u https://sangtacviet.app/truyen/dich/1/53028/ --smoke-test
```

### 3. Cào toàn bộ truyện (chạy ngầm)
```bash
python main.py -u https://sangtacviet.app/truyen/dich/1/53028/
```

### 4. Cào giới hạn số chương (ví dụ 20 chương)
```bash
python main.py -u https://sangtacviet.app/truyen/dich/1/53028/ -l 20
```

### 5. Mở cửa sổ Chromium thực tế để quan sát (Headed mode)
```bash
python main.py -u https://sangtacviet.app/truyen/dich/1/53028/ -l 5 --headed
```

---

## 📦 Cấu Trúc File Đầu Ra (output/{story_id}.jsonl)
Mỗi dòng trong file JSONL là 1 object JSON hoàn chỉnh:
```json
{
  "story_id": "53028",
  "story_title": "(lấp hố Ciweimao)Tổng mạn...",
  "chapter_id": "1",
  "chapter_title": "Chương 63: Ta đang cố gắng không để cho mình biến thành kẻ tồi a",
  "url": "https://sangtacviet.app/truyen/dich/1/53028/1/",
  "content_vi": "Văn bản tiếng Việt phân chia đoạn văn tự nhiên (sẵn sàng đọc TTS)...",
  "content_zh": "Văn bản tiếng Trung gốc...",
  "content_hanviet": "Văn bản âm Hán Việt...",
  "crawled_at": "2026-09-17T10:35:00.000Z"
}
```
