# Contracts — hợp đồng dữ liệu, sự kiện và công cụ

Đây là **nguồn sự thật duy nhất** về hình dạng dữ liệu đi giữa các thành phần của nền tảng AML
Level 1. Mọi producer và consumer phải tuân theo các file trong thư mục này; không thành phần nào
được tự định nghĩa lại một cấu trúc đã có ở đây.

Cơ sở thiết kế: *Kiến trúc chi tiết nền tảng AML Level 1 cho ngân hàng*, phiên bản 1.0 (05/08/2026)
— mục 5.2 (event envelope), 6.2 (mô hình thực thể cốt lõi), 7.2 (typology registry), 8.3/8.5/8.8
(agent state, tool gateway, structured output), 10.2 (event topics), phụ lục B (tool call contract).

---

## 1. Tại sao contract nằm ở repo, không nằm trong đầu người viết code

Nguyên tắc kiến trúc số 8 là **version everything**, số 9 là **replayable and auditable**. Cả hai
chỉ thực hiện được khi hình dạng dữ liệu là một artifact có phiên bản, review được, và test được —
không phải một thoả thuận miệng giữa hai người ngồi cạnh nhau.

Cụ thể, contract ở đây cho phép:

- Producer và consumer phát triển **độc lập** — chỉ cần bám vào file schema, không cần đợi nhau.
- CI chặn merge khi có breaking change không khai báo (`tests/test_contracts/`).
- Replay một quyết định cũ với đúng phiên bản schema tại thời điểm đó.

---

## 2. Cấu trúc

| Thư mục | Nội dung | Ai đọc |
|---|---|---|
| `common/` | `$defs` dùng chung: định danh, thời gian, provenance, confidence, tiền tệ, reason code, phân loại dữ liệu | Mọi schema khác |
| `events/` | Envelope CloudEvents + payload của từng topic Kafka (mục 10.2 của kiến trúc) | Producer/consumer event bus |
| `canonical/` | Thực thể ở vùng CANONICAL/GOLD (mục 6.2) | Data platform, detection, case |
| `agent/` | Tool call contract, agent state, structured output (mục 8) | AI Agent team |
| `registry/` | Typology registry (mục 7.2) | AML SME, detection |
| `ingestion/` | Hợp đồng tầng nạp dữ liệu IBM AML **đang chạy thật** (chuyển từ `schemas/`) | Pipeline Kafka → Flink → HDFS |

`ingestion/` khác các thư mục còn lại ở một điểm quan trọng: **nó mô tả hệ thống đang chạy hôm nay**.
Các thư mục khác mô tả mô hình chuẩn mà nền tảng đang tiến tới. Đừng nhầm hai loại — xem mục 6.

---

## 3. Quy ước bắt buộc trong mọi contract

Bảy quy ước dưới đây áp dụng cho **mọi** schema, không có ngoại lệ. Chúng đến thẳng từ các nguyên
tắc kiến trúc, không phải sở thích phong cách.

1. **`schema_version` là trường bắt buộc.** Consumer phải từ chối bản ghi có version không nhận ra
   thay vì đoán.
2. **Thời gian tách bạch** (mục 5.3): `event_time` (việc xảy ra lúc nào), `ingestion_time` (nền tảng
   biết lúc nào), `posting_time` (hạch toán lúc nào), `available_from` (được phép dùng để suy luận
   từ lúc nào). Gộp chúng lại là cách nhanh nhất để tạo ra rò rỉ dữ liệu tương lai.
3. **Số tiền là chuỗi thập phân**, không phải số dấu phẩy động. Lý do ở mục 4.
4. **Mọi claim trỏ tới evidence.** Cấu trúc nào khẳng định điều gì về khách hàng đều phải mang
   `evidence_refs` (nguyên tắc *evidence-first*).
5. **Mọi liên kết suy luận mang `confidence` và `provenance`.** Link probabilistic không bao giờ
   được ghi như fact (mục 6.3).
6. **`additionalProperties: false`** ở mọi object. Trường lạ là lỗi, không phải dữ liệu bổ sung
   được im lặng bỏ qua.
7. **Không có trường nhãn ẩn** (`is_laundering` thật, `true_role`, `hidden_*`) trong bất kỳ contract
   nào thuộc `events/`, `canonical/` hay `agent/`. Nhãn sống ở vùng LABEL/EVAL, tách quyền và tách
   vật lý (mục 6.1).

---

## 4. Vì sao số tiền là chuỗi, không phải number

Kiến trúc mục 5.2 minh hoạ `"amount": 25000000` dưới dạng số. Contract ở đây cố ý **khác** ví dụ
minh hoạ đó, và đây là một quyết định có chủ đích chứ không phải sai sót khi chép lại:

- Phát hiện structuring dựa vào việc so sánh với ngưỡng. Một khoản 299.999.999,99 VND bị làm tròn
  thành 300.000.000 bởi IEEE-754 sẽ đổi kết quả của một luật AML — sai theo hướng bỏ sót.
- Backend hiện tại đã serialize `NUMERIC` của PostgreSQL thành chuỗi (`src/api/routes.py`), nên
  chuỗi thập phân là lựa chọn **nhất quán với mã đang chạy**, không phải một quy ước mới.
- Pipeline nạp dữ liệu hiện tại dùng `BigDecimal`/`Decimal` ở cả hai đầu vì đúng lý do này.

Định dạng: chuỗi thập phân có dấu, không có dấu phân cách nghìn, không ký hiệu tiền tệ —
`"25000000"`, `"1234.56"`, `"-500.00"`. Tiền tệ nằm ở trường riêng theo ISO 4217.

---

## 5. Quy tắc thay đổi và tương thích

### Thay đổi không phá vỡ tương thích — được phép trong cùng version

- Thêm một trường **tuỳ chọn** có giá trị mặc định rõ ràng.
- Nới lỏng một ràng buộc (mở rộng `enum`, tăng `maxLength`).
- Sửa `description`.

### Thay đổi phá vỡ tương thích — bắt buộc version mới

- Thêm trường bắt buộc, xoá trường, đổi tên trường.
- Đổi kiểu dữ liệu, thu hẹp `enum`, siết ràng buộc.
- Đổi ý nghĩa của một trường mà giữ nguyên tên. **Đây là loại nguy hiểm nhất** vì không công cụ nào
  bắt được: schema vẫn hợp lệ, dữ liệu vẫn parse, chỉ có kết luận là sai.

Quy trình cho thay đổi phá vỡ tương thích:

1. Tạo file mới `<tên>.v<N+1>.schema.json`, **giữ nguyên** file cũ.
2. Với event: tạo topic mới `<tên>.v<N+1>`; không đổi ý nghĩa topic đang chạy.
3. Viết migration note trong PR: ai là consumer, họ chuyển đổi thế nào, khi nào topic cũ ngừng.
4. Chạy song song hai version cho tới khi mọi consumer đã chuyển. Không có ngoại lệ "chỉ có mỗi
   team mình dùng" — điều đó đúng cho tới ngày nó không còn đúng.
5. Cập nhật `docs/repository/CONTRACT_CHANGELOG.md`.

---

## 6. Trạng thái hiện thực — đọc kỹ trước khi dùng

Không phải contract nào ở đây cũng đã có code chạy. Nhầm lẫn điều này là cách nhanh nhất để xây
một thứ tưởng là tích hợp được nhưng không có đầu kia.

| Contract | Trạng thái | Ghi chú |
|---|---|---|
| `ingestion/aml-transaction-v1` | **ĐANG CHẠY** | Producer `python -m src.aml` → Kafka → Flink → HDFS. Có test hai đầu. |
| `canonical/*` | **CHƯA HIỆN THỰC** | Mô hình đích. Lược đồ PostgreSQL hiện tại (`db/init/`) chưa khớp hoàn toàn. |
| `events/bank.*` | **CHƯA HIỆN THỰC** | Chưa có CDC/stream từ core banking. Đây là contract để đội tích hợp bám theo. |
| `events/aml.*` | **CHƯA HIỆN THỰC** | Detection plane chưa phát event. |
| `agent/*` | **CHƯA HIỆN THỰC** | `src/agents/` hiện là khung mẫu. Đây là contract mà agent thật phải tuân theo. |
| `registry/typology` | **CHƯA HIỆN THỰC** | Chưa có typology registry chạy thật. |

Khi một contract chuyển sang **ĐANG CHẠY**, cập nhật bảng này trong cùng PR hiện thực nó.

---

## 7. Kiểm chứng

```bash
make contracts-check        # validate mọi schema + mọi example
pytest tests/test_contracts # tương đương, chạy trong CI trên mọi PR
```

Bộ kiểm thử này kiểm ba thứ:

1. Mọi file `*.schema.json` là JSON Schema draft 2020-12 hợp lệ.
2. Mọi `$ref` phân giải được (không có tham chiếu treo).
3. Mọi file trong `examples/` khớp đúng schema mà nó khai báo — và các ví dụ `*-invalid.json` phải
   **thật sự bị từ chối**. Một contract chưa từng từ chối cái gì thì chưa chứng minh được nó chặn
   được gì.

---

## 8. Sở hữu

Toàn bộ `contracts/` yêu cầu review của Bảo (kiến trúc/hợp đồng, xem `.github/CODEOWNERS`). Đây
không phải quan liêu: contract là chỗ duy nhất mà một thay đổi nhỏ của một người làm hỏng việc của
ba người còn lại mà không ai thấy cho tới lúc tích hợp.

Đề xuất nội dung nghiệp vụ cho contract thuộc về người sở hữu miền tương ứng — typology và reason
code do AML SME quyết định, không phải người viết JSON.
