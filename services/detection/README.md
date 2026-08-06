# services/detection — Detection & Scoring plane

**Trạng thái: CHƯA CÓ CODE.** Thư mục này là nhà chờ sẵn.

Cơ sở: kiến trúc mục 7 (Detection Engine), mục 4 (mặt phẳng 3).

---

## Phạm vi

Detection Engine là một **ensemble nhiều phương pháp**, không phải một mô hình duy nhất. Giá trị
tăng thêm của sản phẩm không nằm ở việc thay rule bằng LLM, mà ở khả năng kết hợp behavioral, graph
và cross-channel evidence với feedback có kiểm soát.

Pipeline tám bước (mục 7.1). Đề xuất bố cục thư mục theo đúng các bước đó:

| Thư mục | Bước | Đầu ra |
|---|---|---|
| `rules/` | 2–3: hard controls, screening, rules/CEP | ngưỡng, velocity, sequence, burst, structuring |
| `behavioral/` | 4: behavioral/peer | độ lệch so với chính mình và so với nhóm tương đương |
| `graph/` | 5: graph | shared device, fan-in/out, community, path-to-risk, role feature |
| `fusion/` | 7–8: score fusion, alert aggregation | điểm đã hiệu chỉnh, ứng viên typology, alert đã gom |

Bước 6 (ML supervised/unsupervised) đặt ở `behavioral/` hoặc `graph/` tuỳ loại đặc trưng nó dùng —
không tách thư mục riêng, vì tách theo "có phải ML không" là cách chia sai: cái quyết định là nó
nhìn dữ liệu gì.

---

## Contract phải tuân theo

| Đọc vào | Ghi ra |
|---|---|
| `contracts/events/aml.feature.updated.v1` | `contracts/events/aml.detection.result.v1` |
| `contracts/canonical/*` | `contracts/events/aml.alert.created.v1` (chỉ `fusion/`) |
| `contracts/registry/typology.v1` | |

---

## Bốn ràng buộc không được nới

1. **Mọi kết quả đều phát ra, kể cả khi không vượt ngưỡng.** Bản ghi `triggered: false` là mẫu số để
   đo bỏ sót khi tuning ngưỡng về sau. Lọc bỏ chúng là vứt đi khả năng biết mình đang bỏ sót gì.
2. **Tối thiểu ba reason code cho mỗi alert.** Đây là quy tắc NT7, đã được cưỡng chế ở
   `contracts/events/aml.alert.created.v1.schema.json` (`minItems: 3`) và ở lược đồ cơ sở dữ liệu
   hiện tại. Điểm rủi ro không bao giờ được hiển thị một mình.
3. **Không tạo một alert cho mỗi rule hit.** Gom theo thực thể, mạng lưới, typology và cửa sổ thời
   gian (mục 7.3). Không gom thì analyst nhận về nhiễu chứ không phải tín hiệu.
4. **Feedback của analyst không cập nhật mô hình trực tiếp.** Nó đi qua label review và release
   pipeline. Nối thẳng vòng phản hồi là cách nhanh nhất để mô hình học chính thiên kiến của quy
   trình vận hành.

---

## Bắt đầu từ đâu

Lộ trình (mục 16) đặt Detection Core ở giai đoạn 1 và Behavioral & Graph ở giai đoạn 2. Thứ tự đó
có lý do: rules cho một đường cơ sở đo được, và không có đường cơ sở thì không chứng minh được
behavioral/graph có thêm được gì.

Điều kiện qua cổng giai đoạn 2: point-in-time test đạt, false-link review đã làm, và benchmark trên
bộ hidden case cho kết quả tốt hơn baseline **ở cùng một alert budget** — so sánh ở alert budget
khác nhau là so sánh vô nghĩa.
