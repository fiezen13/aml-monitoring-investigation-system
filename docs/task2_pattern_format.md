# Báo cáo phân tích format — file pattern IBM LI-Small

**Mục đích:** Trước khi viết parser Task 2, nhóm cần hiểu file mô tả kịch bản rửa tiền của IBM được tổ chức thế nào, đơn vị “một bản ghi” là gì, và thông tin nào dùng để ánh xạ sang typology FIN-07 (T01–T10).

**File đã kiểm tra:** `data/raw/ibm-aml/LI-Small_Patterns.txt`
(Lưu ý: file nằm trong thư mục raw cùng `LI-Small_Trans.csv`, không phải `data/LI-Small_Patterns.txt` ở thư mục gốc.)

**Metadata / checksum:** `data/processed/pattern_file_metadata.json`

---

## 1. Bối cảnh

Dataset IBM AML gồm hai phần chính:

1. File giao dịch (`LI-Small_Trans.csv`) — đã nạp ở Task 1 thành bảng `transaction` / `account`.
2. File pattern (`LI-Small_Patterns.txt`) — mô tả các **kịch bản rửa tiền đã cài sẵn** trong dữ liệu giả lập.

Task 2 chỉ làm việc với file (2): đọc cấu trúc, liệt kê loại kịch bản, rồi ánh xạ sang T01–T10. Báo cáo này ghi lại kết quả đọc thử 50 dòng đầu và quét toàn file.

---

## 2. File trông như thế nào?

Đây là file **text thuần**, không phải một bảng CSV độc lập. Nội dung lặp lại các khối (block) theo khuôn:

```text
BEGIN LAUNDERING ATTEMPT - <LOẠI_KỊCH_BẢN>[:  mô tả thêm nếu có]
dòng giao dịch 1
dòng giao dịch 2
...
END LAUNDERING ATTEMPT - <LOẠI_KỊCH_BẢN>
```

Ví dụ mở đầu file:

- Một block `FAN-IN` với mô tả “Max 3-degree Fan-In”, bên trong 3 dòng chuyển tiền dồn về cùng một tài khoản nhận.
- Tiếp theo lại `FAN-IN` nhưng “Max 8-degree”.
- Rồi `GATHER-SCATTER`, `RANDOM`, `SCATTER-GATHER`, `FAN-OUT`, …

Mỗi dòng bên trong block trông giống một dòng trong file giao dịch (timestamp, ngân hàng/tài khoản gửi–nhận, số tiền, tiền tệ, kênh, và cờ laundering = 1).

---

## 3. Trả lời các câu hỏi then chốt

### Một dòng có phải là một record không?

**Không** — nếu “record” ở đây nghĩa là một kịch bản pattern cần map sang T01–T10.

Một dòng trong block chỉ là **một giao dịch thuộc kịch bản đó**. Parse theo từng dòng sẽ nhầm đơn vị: ta sẽ có hàng nghìn “record” giao dịch thay vì khoảng một trăm kịch bản.

### Một block có phải là một record không?

**Đúng.** Đơn vị làm việc chính của Task 2 là một cặp:

`BEGIN LAUNDERING ATTEMPT …` → các dòng giao dịch → `END LAUNDERING ATTEMPT …`

Mỗi block như vậy là **một lần cài kịch bản** (pattern instance / one laundering attempt). Toàn file có **117** block BEGIN khớp với **117** block END.

### Một block có chứa nhiều attempt không?

**Không.** Mỗi block là **một** attempt. File chỉ xếp nhiều attempt nối tiếp nhau, cách nhau bằng dòng trống.

### Pattern type (loại kịch bản) nằm ở đâu?

Nằm ngay trên dòng mở block, sau dấu gạch ngang:

```text
BEGIN LAUNDERING ATTEMPT - FAN-IN:  Max 3-degree Fan-In
                                 ^^^^^^
                                 loại kịch bản
```

Phần sau dấu `:` (ví dụ “Max 3-degree Fan-In”) là **mô tả bổ sung**, không phải một loại riêng. Dòng `END` lặp lại cùng tên loại để đóng block.

Các loại xuất hiện trong LI-Small (đếm theo dòng BEGIN):

| Loại IBM | Số lần xuất hiện |
|----------|------------------|
| FAN-OUT | 19 |
| STACK | 18 |
| BIPARTITE | 16 |
| RANDOM | 15 |
| SCATTER-GATHER | 13 |
| FAN-IN | 12 |
| GATHER-SCATTER | 12 |
| CYCLE | 12 |
| **Tổng** | **117** |

### Có Instance ID sẵn trong file không?

**Không.** IBM không đánh số sẵn kiểu `PATTERN_001`. Khi parse, cần **tự tạo ID ổn định** (ví dụ số thứ tự block trong file, hoặc hash nội dung block), để lần chạy sau vẫn ra cùng ID.

### Có tham chiếu giao dịch / tài khoản không?

**Có.** Mỗi dòng trong block chứa bank + account gửi/nhận (và các trường tiền tệ, kênh…), cùng kiểu thông tin với file Trans. Điều đó cho phép *sau này* nối sang bảng `transaction` nếu cần.

Với phạm vi hẹp Task 2 hiện tại, **chưa bắt buộc** gắn typology lên từng giao dịch; chỉ cần dùng block để biết loại kịch bản và độ phủ T01–T10.

---

## 4. Thông tin kỹ thuật (để tái lập)

| Mục | Giá trị |
|-----|---------|
| Kích thước | 99 156 bytes |
| Số dòng | 1 374 |
| SHA-256 | `734c15b7ff4be1a04a3529bd1524b92c1e8b62289d3ce4881423596ee47a208f` |
| MD5 | `d11028b5ee3c5a887f4f6d7033da8cb8` |
| Số block BEGIN / END | 117 / 117 |

Checksum được lưu kèm trong `data/processed/pattern_file_metadata.json` để kiểm chứng file nguồn không đổi giữa các lần chạy.

---

## 5. Cách hiểu “record” khi viết parser

Để tránh nhầm lẫn khi code Task 2, nhóm thống nhất:

| Khái niệm | Nghĩa trong file này |
|-----------|----------------------|
| Pattern instance | Một block BEGIN…END — đơn vị đếm và inventory |
| Pattern type | Token sau `BEGIN LAUNDERING ATTEMPT - ` (trước dấu `:` nếu có) |
| Type detail | Phần sau `:` — ghi chú, không tách thành type mới |
| Dòng giao dịch | Con của instance; dùng cho tham chiếu, không dùng làm đơn vị map typology ở Sprint 1 |
| Instance ID | Tự sinh, deterministic |

Ánh xạ sang FIN-07 T01–T10 nên làm ở mức **pattern type** (kèm ghi chú detail khi cần), không map từng dòng giao dịch trong bước này.

---

## 6. Hệ quả cho Task 2

1. **Parser** nhận diện format block BEGIN/END; nếu file không đúng khuôn này thì báo lỗi rõ, không cố đoán.
2. **Inventory** khoảng 117 instance, 8 loại IBM như bảng trên.
3. **Không** chạy lại ETL bảng `transaction` / `account` của Task 1.
4. **Không** bắt buộc gắn nhãn typology lên từng giao dịch trong Task 2.
5. Giữ checksum file pattern để đảm bảo tái lập được kết quả phân tích.

Tài liệu này là đầu vào cho bước tiếp theo: lập bảng quy tắc ánh xạ type IBM → T01–T10 và báo cáo độ phủ typology.

**Schema chốt (Phase 3):** xem [task2_schema.md](task2_schema.md) và module `src/data/typology_schema.py`.
