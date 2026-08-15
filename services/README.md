# services/ — chỗ đặt các thành phần theo sáu mặt phẳng kiến trúc

Thư mục này là **nhà chờ sẵn** cho các thành phần chưa viết, để khi bắt đầu không ai phải hỏi "đặt
code ở đâu". Mã đang chạy **không** bị chuyển vào đây — nó ở nguyên chỗ cũ, xem bảng bên dưới.

Cơ sở: *Kiến trúc chi tiết nền tảng AML Level 1*, mục 4 (sáu mặt phẳng) và phụ lục A (component
catalog).

---

## Sáu mặt phẳng và code tương ứng

| Mặt phẳng | Trách nhiệm | Code hiện ở đâu | Trạng thái |
|---|---|---|---|
| 1. Integration & Event | Nhận, chuẩn hoá envelope, kiểm schema, replay, DLQ | `src/aml/` (producer), `flink/aml-ingestion/` (Flink job) | **ĐANG CHẠY** — chỉ mới có đường CSV → Kafka → HDFS |
| 2. Data & Intelligence | Canonical data, identity graph, feature, evidence, lineage | `db/init/`, `src/behavior/` | **MỘT PHẦN** — có lược đồ và batch LI-Small, chưa có feature platform |
| 3. Detection & Scoring | Rules, CEP, behavioral, graph, ML, score fusion | `services/detection/` | **CHƯA CÓ** |
| 4. Case & Workflow | Alert queue, case state, SLA, maker-checker, EDD/STR | `src/api/`, `src/worker/`, `src/domain.py` | **MỘT PHẦN** — có máy trạng thái và quy trình phê duyệt |
| 5. AI Agent | Thu thập bằng chứng, giả thuyết, giải thích, draft | `services/agent-runtime/` (đích), `src/agents/` (khung mẫu hiện tại) | **KHUNG MẪU** |
| 6. Platform/Governance/Security | IAM, audit, MLOps, observability, HA/DR | `ci/`, `deploy/`, `jenkins/`, `db/init/002`, `db/init/003` | **MỘT PHẦN** |

Giao diện analyst nằm ở `web/` — nó phục vụ mặt phẳng 4 và 5, không phải một mặt phẳng riêng.

---

## Quy tắc chung cho mọi thành phần đặt ở đây

Bốn quy tắc này không phải phong cách, chúng đến thẳng từ nguyên tắc kiến trúc:

1. **Đọc và ghi qua contract.** Mọi đầu vào/đầu ra phải khớp một schema trong `contracts/`. Không
   thành phần nào tự định nghĩa lại một cấu trúc đã có ở đó.
2. **Không LLM trên đường quyết định đồng bộ** (nguyên tắc số 3). Đường chặn/cho phép giao dịch
   không được phụ thuộc vào mô hình ngôn ngữ.
3. **Point-in-time correctness** (nguyên tắc số 2). Mọi phép tính phải nhận `as_of_time` và chỉ dùng
   dữ liệu có `available_from` sớm hơn mốc đó. Đây là ranh giới giữa một chỉ số đo thật và một chỉ
   số đẹp giả tạo do rò rỉ dữ liệu tương lai.
4. **Không đọc vùng LABEL/EVAL từ đường suy luận.** Nhãn chỉ dùng khi đánh giá. Ràng buộc này đã
   được cưỡng chế ở tầng PostgreSQL bằng vai trò `fin07_agent` (`db/init/003_agent_readonly_role.sh`)
   — đừng tìm cách đi vòng qua nó bằng một kết nối khác.

---

## Trước khi thêm một thư mục mới ở đây

Đừng tạo trước một thư mục cho thứ chưa ai bắt đầu viết. Thư mục rỗng kèm README đẹp trông giống
tiến độ nhưng không phải tiến độ, và nó làm người mới mất thời gian đi tìm code không tồn tại.

Ba thư mục hiện có tồn tại vì chúng nằm trong lộ trình Level 1 đã chốt (mục 16 của kiến trúc), có
chủ sở hữu, và có contract sẵn để bám vào.
