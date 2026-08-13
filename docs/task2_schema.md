# Task 2 — Schema chốt (Phase 3)

Tài liệu này khóa contract dữ liệu trước khi viết parser / bảng ánh xạ typology.
Phạm vi: **không** ETL lại Task 1, **không** gắn `label_typology` lên từng giao dịch, **không** xây detector.

Tham chiếu format nguồn: [task2_pattern_format.md](task2_pattern_format.md).

---

## 1. Catalog envelope (metadata cấp bộ rule)

`source_file` / checksum **không** lặp trên từng rule. Chúng nằm ở cấp catalog:

```json
{
  "mapping_version": "v1.0",
  "source": {
    "file": "data/raw/ibm-aml/LI-Small_Patterns.txt",
    "sha256": "734c15b7ff4be1a04a3529bd1524b92c1e8b62289d3ce4881423596ee47a208f",
    "parser_version": "v1.0"
  },
  "rules": [ ]
}
```

| Trường | Ý nghĩa |
|--------|---------|
| `mapping_version` | Phiên bản bộ rule (so sánh / audit) |
| `source.file` | Đường dẫn file pattern dùng khi review |
| `source.sha256` | Checksum file nguồn |
| `source.parser_version` | Phiên bản logic parse instance |
| `rules` | Danh sách `typology_mapping_rules` |

Chỉ đưa checksum vào từng dòng rule nếu sau này một catalog được dựng từ **nhiều** file nguồn khác nhau.

---

## 2. `typology_mapping_rules`

Bảng / object quy tắc ánh xạ **pattern type → FIN-07 typology**.

| Trường | Kiểu | Bắt buộc | Ghi chú |
|--------|------|----------|---------|
| `ibm_pattern_type` | string | Có | Canonical key (vd `CYCLE`, `FAN-IN`) — join với instance |
| `display_name` | string | Có | Hiển thị (vd `Cycle`) |
| `primary_typology` | `T01`…`T10` hoặc `null` | — | Nullable theo status |
| `secondary_typologies` | list[`T01`…`T10`] | Có | Mặc định `[]`; **không** nhét secondary vào notes |
| `mapping_status` | enum | Có | Xem mục 4 |
| `mapping_reason` | string | **Luôn có, không rỗng** | Kể cả khi `MAPPED` |
| `mapping_version` | string | Có | Thường trùng catalog `mapping_version` |
| `reviewed_by` | string \| null | — | Người duyệt |
| `reviewed_at` | datetime \| null | — | Thời điểm duyệt |

### Invariant

1. `ibm_pattern_type` **duy nhất** trong một `mapping_version`.
2. `mapping_reason` luôn không rỗng (mọi status, kể cả `MAPPED`).
3. `primary_typology` ∈ {T01…T10} hoặc `null`.
4. Mọi phần tử `secondary_typologies` ∈ {T01…T10}.
5. `primary_typology` **không** xuất hiện trong `secondary_typologies`.
6. `MAPPED` ⇒ `primary_typology` ≠ `null`.
7. `OUT_OF_SCOPE` và `UNMAPPED` thường có `primary_typology = null`.
8. `PARTIAL` có thể có hoặc không có primary (xem mục 4).

### Ví dụ

```json
{
  "ibm_pattern_type": "CYCLE",
  "display_name": "Cycle",
  "primary_typology": "T03",
  "secondary_typologies": [],
  "mapping_status": "MAPPED",
  "mapping_reason": "Chuỗi chuyển tiền tạo đường đi khép kín và quay lại nút trước đó, phù hợp định nghĩa giao dịch vòng (T03).",
  "mapping_version": "v1.0",
  "reviewed_by": null,
  "reviewed_at": null
}
```

`PARTIAL` chưa chốt primary:

```json
{
  "ibm_pattern_type": "GATHER-SCATTER",
  "display_name": "Gather-Scatter",
  "primary_typology": null,
  "secondary_typologies": ["T02", "T04"],
  "mapping_status": "PARTIAL",
  "mapping_reason": "Vừa có gom vào vừa tỏa ra; liên quan T02 và T04 nhưng chưa đủ cơ sở chọn primary chắc.",
  "mapping_version": "v1.0",
  "reviewed_by": null,
  "reviewed_at": null
}
```

---

## 3. `ibm_pattern_instance`

Một dòng = **một block BEGIN…END** đã parse (xem báo cáo format).

| Trường | Kiểu | Bắt buộc | Ghi chú |
|--------|------|----------|---------|
| `instance_id` | string | Có | Sinh ổn định nếu nguồn không có ID |
| `raw_pattern_name` | string | Có | Token type đúng như trên dòng BEGIN (trước khi alias) |
| `pattern_type` | string | Có | Canonical — join `rules.ibm_pattern_type` |
| `source_record_index` | int | Có | **0-based** trong code; báo cáo người đọc có thể +1 |
| `source_start_line` | int \| null | — | 0-based hoặc 1-based dòng file — chốt **1-based** cho người đọc (số dòng editor) |
| `source_end_line` | int \| null | — | Cùng quy ước với start |
| `referenced_accounts` | list có cấu trúc \| null | — | v1 có thể `null` nếu chưa extract |
| `referenced_transactions` | list có cấu trúc \| null | — | v1 có thể `null` |
| `parse_status` | `OK` \| `WARN` \| `ERROR` | Có | **Không** dùng chung enum mapping |
| `parse_notes` | string \| null | — | |
| `source_file` | string | Có | |
| `source_checksum` | string | Có | sha256 file nguồn |

`source_start_line` / `source_end_line`: dùng **1-based** (khớp số dòng trong editor / báo cáo).
`source_record_index`: **0-based** (index instance trong danh sách parse).

---

## 4. Enum `mapping_status`

| Giá trị | Định nghĩa |
|---------|------------|
| `MAPPED` | Pattern khớp rõ ít nhất một typology, **đã chọn primary**, và bao phủ đủ các dấu hiệu cốt lõi cần thiết. |
| `PARTIAL` | Chỉ bao phủ một phần định nghĩa T0x, **hoặc** overlap nhiều typology nhưng chưa đủ cơ sở chốt primary chắc. `primary_typology` có thể `null` trong trường hợp thứ hai; hoặc có primary nếu đã chọn tương đối chắc nhưng vẫn chỉ cover một phần. |
| `UNMAPPED` | Nằm trong phạm vi nghiệp vụ FIN-07 nhưng chưa đủ bằng chứng để ánh xạ vào T01–T10. |
| `OUT_OF_SCOPE` | Đã hiểu pattern, nhưng nhóm **chủ động** không dùng trong cam kết T01–T10 của MVP. |

`mapping_reason` **bắt buộc không rỗng với mọi trạng thái**, kể cả `MAPPED`.

---

## 5. Enum `parse_status` (instance)

| Giá trị | Nghĩa |
|---------|--------|
| `OK` | Block parse thành công |
| `WARN` | Parse được nhưng thiếu field / bất thường nhẹ |
| `ERROR` | Không parse được block |

---

## 6. Canonical naming

Join key dùng token UPPER dạng IBM BEGIN, ví dụ:

`CYCLE`, `FAN-IN`, `FAN-OUT`, `GATHER-SCATTER`, `SCATTER-GATHER`, `STACK`, `BIPARTITE`, `RANDOM`

Luồng chuẩn hóa:

1. `strip` → `upper`
2. `_` → `-`; gộp khoảng trắng → `-`
3. Áp **alias map** cho synonym (`FANOUT` → `FAN-OUT`, …)
4. Giữ `raw_pattern_name` để audit

Implement: `src/data/typology_schema.py` (`canonicalize_pattern_type`, `PATTERN_TYPE_ALIASES`, validators).

---

## 7. Ngoài phạm vi schema này

- Gắn typology lên từng dòng `transaction`
- Detector / feature graph
- Many-to-many chính thức ngoài `primary` + `secondary_typologies`
