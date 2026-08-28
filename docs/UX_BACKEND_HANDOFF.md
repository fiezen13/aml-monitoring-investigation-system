# Bàn giao kỹ thuật — phần backend còn lại của đợt UI/UX (chuyên viên AML)

Tài liệu này liệt kê các vấn đề UX **có gốc ở backend/dữ liệu** mà đợt display-only
không chữa được, kèm gốc rễ đã xác minh, thay đổi đề xuất, và kế hoạch thực thi an
toàn. Phần frontend (mục 2–11 của bản đánh giá) đã sửa và deploy lên
https://amlmonitoring.site.

> Cảnh báo chung: mọi thay đổi dưới đây tác động **điểm rủi ro / ưu tiên / vụ việc**
> của một hệ giám sát AML đang vận hành. Chấm sai → ưu tiên sai cảnh báo rửa tiền.
> Phải kiểm định offline trước, và migrate dữ liệu production có backup + rollback.

---

## 1. Risk score bão hoà ở 100 (không phân hạng được)

**Gốc rễ:** điểm bị kẹp trần.
- `src/detection/rules.py` — `risk_score()` trả `round(min(score, 100.0), 2)`.
- `src/services/if_alert_publish.py:235` — `risk = min(max(risk_score,0),100)`.

Khi tổng đóng góp thường vượt 100, phần lớn cảnh báo dồn về đúng 100 → cột risk mất
khả năng xếp hạng.

**Đề xuất (cần đồng nghiệp sở hữu detection + kiểm định):**
- Chuẩn hoá điểm sang thang phân tán (vd min-max/percentile theo phân phối thực,
  hoặc log-squash trước khi kẹp) để giữ thứ hạng thay vì dồn trần.
- Hoặc tách **severity band** rời khỏi điểm thô để phân hạng không phụ thuộc điểm bão hoà.
- Kiểm định: so phân phối điểm trước/sau trên tập lịch sử; đảm bảo thứ hạng tương
  đối của cảnh báo dương thật không xấu đi.

**Dữ liệu hiện có:** cảnh báo cũ vẫn 100 tới khi **chấm lại**. Cần job re-score đọc
`alert_reason`/đặc trưng rồi cập nhật `alert.risk_score` (thao tác ghi trên prod).

---

## 2. Priority = hàm của risk (không độc lập)

**Gốc rễ:** `src/investigation/repository.py:104`
```
priority = "critical" if score>=90 else "high" if score>=80 else "medium" if score>=60 else "low"
```
Priority suy thẳng từ risk → risk bão hoà thì priority luôn "critical".

**Đề xuất:** priority = f(risk, **SLA**, **exposure**, bối cảnh pháp lý) như bản đánh
giá nêu. Cần bổ sung đầu vào:
- SLA: định nghĩa hạn xử lý theo severity/loại → suy "quá hạn".
- Exposure: tổng amount/số counterparty của chủ thể (tính từ giao dịch).
Khi chưa có các đầu vào này, priority độc lập là **chưa khả thi** — đừng chế số.

---

## 3. Vụ việc 1:1 với cảnh báo + tiêu đề kỹ thuật

**Gốc rễ:** `src/investigation/repository.py:100-114` — alert chưa có case thì luôn
tạo case MỚI, `title = f"Explainable investigation for {alert_id}"`.

**Đề xuất:**
- Gom theo chủ thể/bối cảnh: trước khi tạo mới, tìm case đang mở cùng
  `subject_account_key` (và/hoặc cùng cửa sổ thời gian) để **đính vào** thay vì tạo mới.
- Tiêu đề nghiệp vụ: sinh từ typology chính + chủ thể (FE đã tạm rút gọn hiển thị,
  nhưng nên sửa ở nguồn).
- Migrate: gộp các case 1-alert hiện có theo chủ thể là thao tác ghi lớn trên prod —
  cần kịch bản riêng + rollback; `audit_log` bất biến nên phải ghi sự kiện gộp, không sửa cũ.

---

## 4. Missing ở nguồn (no-data vs score 0)

**Trạng thái:** FE đã phân biệt khi backend đặt cờ `available` cho từng thành phần
điểm (đã dùng ở tab Điều tra AI). Cần rà **mọi detector** đặt `available=false` khi
không chạy/không đủ dữ liệu, thay vì để component score 0.

---

## 5. Nhất quán window/count/amount giữa các service

**Vấn đề:** feature service, transaction service và narrative AI có thể lệch cửa
sổ/đếm/tổng cho cùng một cảnh báo. Đây là lỗi niềm tin nghiêm trọng nhất.

**Đề xuất:** một nguồn sự thật duy nhất cho (window, count, amount) mỗi alert (vd
snapshot ở feature store), các service còn lại đọc lại từ đó thay vì tự tính lại.

---

## 6. Cần dữ liệu ngoài — chưa làm được bằng code

- PEP/Sanctions screening thật (đang là dữ liệu tổng hợp minh hoạ).
- Anomaly baseline (mức lệch so chuẩn) cho bản đồ địa lý.
- Dữ liệu drill-down corridor và provenance lớp dòng tiền (VASP/bridge/gambling).

FE đã ghi rõ giới hạn ở nơi liên quan; chỉ "hoàn thiện" được khi có nguồn dữ liệu.

---

## Tuỳ chọn rủi ro thấp có thể làm ngay (không đổi phương pháp, không ghi lại dữ liệu)

Sắp thứ tự hàng đợi có **tie-break** ở tầng API-đọc (`src/api/routes.py`): giữ
`ORDER BY risk_score DESC` rồi thêm khoá phụ (số cảnh báo trong vụ, số yếu tố, thời
gian tạo) để queue vẫn xếp được việc khi điểm bão hoà. Chỉ đọc, không đụng
detection/scoring, không migrate. Deploy backend cần rebuild container `api` trên VM
(có build-gate + smoke + backup như các đợt web).
