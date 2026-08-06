# services/feature-platform — Feature & Graph plane

**Trạng thái: CHƯA CÓ CODE.** Thư mục này là nhà chờ sẵn.

Cơ sở: kiến trúc mục 6.1 (vùng FEATURE và GRAPH), mục 6.3 (entity resolution).

---

## Phạm vi

Ba thứ, tách biệt nhau:

| Thư mục đề xuất | Nội dung |
|---|---|
| `entity_resolution/` | Gộp định danh từ nhiều nguồn về canonical ID, hai tầng deterministic + probabilistic |
| `graph/` | Dựng đồ thị thời gian: nút, cạnh, valid time, provenance |
| `features/` | Tính feature online và offline từ cùng một định nghĩa |

---

## Contract phải tuân theo

`contracts/canonical/relationship.v1` là contract quan trọng nhất ở đây, và nó là chỗ dễ gây hại
nhất trong toàn bộ nền tảng nếu làm ẩu.

---

## Ba ràng buộc quyết định chất lượng

**Link probabilistic không phải fact.** Contract cưỡng chế: `is_fact` chỉ được `true` khi `method`
là `DETERMINISTIC` hoặc `ANALYST_CONFIRMED`, và `inference_logic` là bắt buộc với mọi cạnh
`PROBABILISTIC`. Một cạnh suy luận được đánh dấu nhầm là fact sẽ lan truyền qua mọi thuật toán đồ
thị dùng nó, và không ai truy ngược lại được nguồn gốc.

Ví dụ cụ thể cho thấy vì sao `inference_logic` phải viết ra: "cùng IMEI trong 41 phiên" và "cùng IP
tĩnh trong 9 phiên, không loại trừ được NAT của nhà mạng" đều là cạnh `SHARED_*`, nhưng độ tin cậy
của chúng khác nhau một trời một vực. Vế thứ hai — phần "không loại trừ được" — chính là thứ phải
được ghi lại.

**Không ghi đè nguồn bằng kết quả entity resolution** (mục 3.2). Định danh gốc giữ nguyên trong
`source_refs`. Entity resolution tạo ra một lớp *thêm vào*, không phải một lớp *thay thế* — vì nó có
thể sai, và khi nó sai thì phải quay lại được.

**Định nghĩa feature online và offline phải là một.** Hai bản hiện thực của cùng một công thức sẽ
lệch nhau, và triệu chứng là mô hình chạy tốt lúc huấn luyện rồi kém hẳn khi lên production —
training/serving skew. Cùng định nghĩa, cùng version, kiểm bằng point-in-time test.

---

## Point-in-time correctness — cái bẫy tốn kém nhất

`as_of_time` là thời điểm feature **mô tả**. `computed_at` là thời điểm phép tính **chạy**. Join
bằng `computed_at` là rò rỉ dữ liệu tương lai: mô hình được nhìn thấy thông tin chưa tồn tại tại
thời điểm nó lẽ ra phải ra quyết định.

Triệu chứng của lỗi này rất đặc trưng: chỉ số offline đẹp bất thường, production không bao giờ đạt
được, và không ai giải thích được vì sao. Nó thường chỉ bị phát hiện sau khi đã tốn nhiều tuần tinh
chỉnh mô hình.

Contract `contracts/events/aml.feature.updated.v1` bắt buộc **cả hai** trường, chính vì lý do này.
