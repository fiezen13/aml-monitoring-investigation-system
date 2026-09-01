# Kế hoạch kiểm thử — FIN-07

Tài liệu này định nghĩa **kiểm cái gì, ở tầng nào, bằng cách nào, và cổng nào
chặn merge**.

Tài liệu liên quan: [danh mục ca kiểm thử](test-cases.md) ·
[báo cáo kiểm thử](test-report.md) · [yêu cầu chức năng](../specification/functional-requirements.md) ·
[thiết kế kỹ thuật](../specification/technical-design.md).

---

## 1. Phạm vi và mục tiêu

| Mục tiêu | Vì sao quan trọng với hệ thống AML |
|---|---|
| Không có đường truy cập trái phép | Phân quyền sai ở hệ AML là sự cố tuân thủ, không phải lỗi giao diện |
| Tác tử không bịa số, không bịa dẫn chứng | Một hồ sơ nghi vấn sai gửi đi tốn kém hơn một hồ sơ không gửi |
| Nhãn không rò rỉ vào detector | Chỉ số đo trên dữ liệu rò rỉ nhãn là chỉ số vô nghĩa |
| Nhật ký kiểm toán không sửa được | Kiểm toán viên phải tái dựng được diễn tiến vụ việc |
| Tài liệu cấu hình không lạc hậu | Biến môi trường thiếu tài liệu là bẫy khi triển khai |
| Hệ thống dựng được từ máy trống | Ban giám khảo phải chạy được, không chỉ đọc được |

**Ngoài phạm vi:** kiểm thử tải, kiểm thử xâm nhập của bên thứ ba, và đo trải
nghiệm người dùng có người thật. Ba hạng mục này chưa làm — nói rõ thay vì để
trống.

---

## 2. Kim tự tháp kiểm thử

| Tầng | Số lượng | Công cụ | Cần hạ tầng |
|---|---|---|---|
| Đơn vị + tích hợp (Python) | **94 file · 679 ca** | pytest, pytest-asyncio | PostgreSQL + Redis thật cho ca gắn nhãn `integration` |
| Đơn vị (giao diện) | **15 file** | Vitest + Testing Library | không |
| Hợp đồng dữ liệu | `make contracts-check` | JSON Schema, ví dụ hợp lệ **và** không hợp lệ | không |
| Kiểm thử job Flink | Maven | JUnit | JDK 11 + Maven |
| Khói đầu–cuối | `ci/smoke.sh`, `scripts/aml/smoke_test.sh` | curl + docker compose | toàn bộ stack |
| Kiểm thử thủ công có bằng chứng | 5 ca Gate 2 + rà soát 5 vai trò | trình duyệt headless, token thật | bản đang chạy |

### 2.1 Phân bố ca kiểm thử Python theo vùng

| Vùng | File | Ca | Kiểm cái gì |
|---|---:|---:|---|
| `test_api` | 18 | 171 | Route, phân quyền, chính sách mặc-định-đóng, phạm vi dữ liệu, copilot |
| `test_investigation` | 9 | 120 | Máy trạng thái tác tử, cổng công cụ, tính nhất quán bằng chứng, ngân sách |
| `test_data` | 8 | 92 | ETL, chia tập, đặc trưng đồ thị, detector chu trình |
| `test_aml` | 7 | 65 | Đường nạp AML, cấu hình, fixture |
| `test_mega_pna` | 6 | 40 | Mô hình đồ thị chấm cạnh |
| `test_bitcoin_aml` | 5 | 35 | Nhánh Elliptic++ |
| `test_detection` | 3 | 26 | Luật nghiệp vụ và detector |
| `test_benchmark` | 2 | 19 | Hợp đồng báo cáo benchmark |
| `test_services` | 2 | 15 | Dịch vụ dùng chung |
| `test_behavior` | 5 | 14 | Isolation Forest, đặc trưng hành vi |
| `test_db` | 6 | 13 | Migration, ràng buộc, bất biến |
| `test_samld` | 7 | 13 | Nhánh SAML-D |
| `test_fusion` | 4 | 11 | Hợp nhất điểm, hiệu chuẩn phân vị |
| `test_worker` | 3 | 8 | Hàng đợi, tác vụ nền |
| `test_models` | 3 | 5 | Hợp đồng đặc trưng, runtime mô hình |
| `test_contracts` | 2 | 5 | Xác thực JSON Schema hai chiều |
| gốc `tests/` | 4 | 27 | Cấu hình, từ vựng nghiệp vụ, quan trắc, backfill |

---

## 3. Chiến lược theo rủi ro

### 3.1 Phân quyền — kiểm bằng liệt kê, không bằng mẫu

Chính sách là **mặc-định-đóng**. Một bài kiểm thử chứng minh **mọi** route
`/api/v1` đều có khai báo chính sách trong `authz.POLICY`; route mới quên khai
báo thì bài kiểm thử đỏ, chứ không phải âm thầm mở.

Ma trận vai × route được kiểm cả **chiều dương** (vai có quyền thì qua cổng) và
**chiều âm** (vai không có quyền thì 403). Chiều âm quan trọng hơn.

> **Bẫy đã gặp thật:** sửa mỗi thân hàm mà quên cổng `authz` thì quy trình kẹt im
> lặng — người dùng đúng vai vẫn bị chặn mà không có thông báo hữu ích. Vì vậy
> quyền được kiểm ở **cả hai tầng**.

### 3.2 Bảng nhãn hiển thị — khoá bằng liệt kê giá trị thật

Các bảng ánh xạ mã sang nhãn tiếng Việt (typology, trạng thái vụ việc, tên nhánh)
có kiểu hỏng đặc trưng: fallback `?? value` khiến mã nội bộ lọt ra giao diện mà
không ai thấy lỗi. Cách chặn là bài kiểm thử **liệt kê đúng tập giá trị thật**
đang có trong cơ sở dữ liệu, không phải kiểm một vài mẫu.

### 3.3 Rò rỉ nhãn

Kiểm thử xác nhận: dữ liệu đặc trưng và hiệu chuẩn chỉ lấy từ tập train; chia tập
theo thời gian; `sample_split` gán theo mốc snapshot; tác tử không có công cụ nào
chạm tới bảng nhãn.

### 3.4 Tác tử

Kiểm ở chế độ `LLM_MODE=mock` — tác tử tất định, **không gọi mạng**. CI không phụ
thuộc vào dịch vụ bên ngoài và không tiêu tốn hạn mức. Đường gọi Gemini thật được
kiểm bằng các ca thủ công có bằng chứng (mục 5).

Trọng tâm: allow-list công cụ từ chối tên ngoài danh sách; tham số được xác thực
trước khi kiểm quyền; ngân sách 5 vòng / 16 lượt gọi công cụ được tôn trọng; chạm
trần thì kết thúc ở `INSUFFICIENT_EVIDENCE` kèm lý do cụ thể.

### 3.5 Bất biến cơ sở dữ liệu

Kiểm rằng `UPDATE` và `DELETE` trên `audit_log` **bị trigger từ chối**, và vai trò
tác tử chỉ có quyền `SELECT`. Đây là kiểm thử ở tầng cơ sở dữ liệu, không phải
tầng ứng dụng — vì ràng buộc cũng nằm ở đó.

---

## 4. Cổng chất lượng

### 4.1 Cục bộ

```bash
make check            # ruff check + toàn bộ pytest
make contracts-check  # xác thực mọi hợp đồng trong contracts/
cd web && npm run typecheck && npm test -- --run && npm run build
```

### 4.2 GitHub Actions — [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml)

Năm job, tất cả phải xanh mới merge được:

| Job | Nội dung |
|---|---|
| `lint` | `ruff check` + `ruff format --check` + shellcheck + kiểm cấu hình quan trắc + kiểm hợp đồng benchmark |
| `test` | pytest có PostgreSQL và Redis thật (service container), kèm coverage và `pytest-report.xml` |
| `web` | `tsc` kiểm kiểu + Vitest + `vite build` |
| `images` | Build và đẩy image api/worker và web lên GHCR |
| `compose-smoke` | `docker compose up` trên máy sạch, **mọi dịch vụ phải xanh** |

Job `compose-smoke` là cổng quan trọng nhất cho việc chấm: nó chứng minh hệ thống
dựng được từ máy trống, không chỉ chạy được trên máy người viết.

### 4.3 Jenkins — [`Jenkinsfile`](../../Jenkinsfile)

Pipeline giao hàng: kiểm tra môi trường → kiểm tra chất lượng (lint ∥ kiểm thử ∥
giao diện, chạy song song) → build image → triển khai staging → **chờ người phê
duyệt** → triển khai production-like.

Bước *chờ phê duyệt* là bắt buộc — không có đường tự động lên môi trường
production-like.

### 4.4 Hai chế độ chạy kiểm thử

[`ci/test.sh`](../../ci/test.sh) tự nhận biết:

- **Đã có sẵn CSDL** (`DATABASE_URL` + `REDIS_URL` đã đặt) — dùng luôn. GitHub
  Actions chạy theo cách này với service container.
- **Chưa có gì** — tự dựng PostgreSQL và Redis bằng
  [`deploy/docker-compose.test.yml`](../../deploy/docker-compose.test.yml), chạy
  xong thì dọn. Jenkins và máy cá nhân chạy theo cách này.

Mỗi lượt chạy dùng tên project riêng và **cổng 0** (Docker tự cấp cổng trống), để
hai job song song trên cùng một agent không giẫm lên CSDL của nhau và không đụng
cổng 5432 của stack phát triển.

### 4.5 Bước tự bỏ qua có thông báo

Kiểm thử job Flink cần JDK 11 và Maven. Không phải agent nào cũng có, và bắt mọi
agent phải có chỉ vì một module là quá tay. Bước này **tự bỏ qua khi thiếu công
cụ, và nói ra rằng nó đã bỏ qua** — không im lặng.

---

## 5. Kiểm thử thủ công có bằng chứng

Hai hạng mục không tự động hoá được, chạy tay và lưu bằng chứng:

| Hạng mục | Nội dung | Kết quả |
|---|---|---|
| **Rà soát chất lượng (QA/QC)** | 5 vai trò × 22 route GET + 7 route ghi, cộng 12 lần gõ thẳng URL trên trình duyệt headless | [báo cáo kiểm thử §2](test-report.md#2-rà-soát-phân-quyền-và-giao-diện) |
| **Gate 2 — đánh giá tác tử** | 5 ca chạy với Gemini **thật**, phủ cả ba nhánh phát hiện | [báo cáo kiểm thử §3](test-report.md#3-đánh-giá-tác-tử-điều-tra-gate-2) |
| **Rà soát chất lượng tác tử** | 300 phiên lấy mẫu theo cặp (detector, nhóm hành vi), chấm bằng phép kiểm tất định | [báo cáo kiểm thử §4](test-report.md#4-rà-soát-chất-lượng-tác-tử-300-phiên) |

**Nguyên tắc chấm:** không hỏi mô hình xem nó tự thấy mình viết tốt chưa. Mọi phép
chấm đều tất định và kiểm chứng lại được.

---

## 6. Quy ước trích dẫn số liệu benchmark

Chỉ báo cáo mang `"schema_version": "fin07.benchmark.v1"` được trích dẫn, và
**chỉ khoá `headline`** trong đó. Mọi giá trị khác — kể cả `f1` nằm trong
`diagnostics` hay `selection` — **không được** đưa vào tài liệu, slide hay báo
cáo. Lý do và cách cưỡng chế ở [`reports/README.md`](../../reports/README.md);
`scripts/validate_benchmarks.py` kiểm quy ước này trong cổng lint.

---

## 7. Dữ liệu kiểm thử

- Fixture nằm ở [`tests/fixtures/`](../../tests/fixtures/), sinh lại được bằng
  `make aml-fixture`.
- Ca gắn nhãn `integration` **tự bỏ qua** khi không nối được PostgreSQL/Redis, để
  bộ kiểm thử vẫn chạy được trên máy chưa dựng hạ tầng.
- Không có dữ liệu khách hàng thật ở bất kỳ tầng nào. Dump PostgreSQL loại trừ
  bảng `app_session`, nên không mang token đăng nhập từ máy này sang máy khác.
