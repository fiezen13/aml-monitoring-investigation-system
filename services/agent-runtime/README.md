# services/agent-runtime — AI Agent plane

**Trạng thái: CHƯA CÓ CODE.** `src/agents/` hiện là khung mẫu hai node của bộ khởi tạo dự án, không
gọi LLM, không gọi tool, không chạm cơ sở dữ liệu. Agent thật sẽ được xây ở đây.

Cơ sở: kiến trúc mục 8 (AI Investigation Agent), phụ lục B (tool call contract), phụ lục C (phân
loại dữ liệu cho prompt).

---

## Mô hình đã chốt

> **deterministic orchestrator + bounded reasoning + controlled tools**

Không triển khai multi-agent tự do trao đổi vô hạn. Không cho model truy cập trực tiếp cơ sở dữ liệu.

Đề xuất bố cục:

| Thư mục | Nội dung | Cần LLM không |
|---|---|---|
| `orchestrator/` | Máy trạng thái, checkpoint, budget, human-in-the-loop | Không — mã tất định |
| `tools/` | Hiện thực từng tool trong allowlist, mỗi tool một schema | Không — executor tất định |
| `policy/` | Tool gateway, ABAC, redaction, ma trận phê duyệt | Không — policy engine |
| `skills/` | Query planner, hypothesis manager, narrative composer, claim checker | Có |

Ba trong bốn thư mục **không cần LLM**. Đó là điểm chính của thiết kế: phần suy luận xác suất bị bao
quanh bởi mã tất định, chứ không phải ngược lại.

---

## Contract phải tuân theo

| Contract | Vai trò |
|---|---|
| `contracts/agent/agent-case-state.v1` | State bền vững, checkpoint được |
| `contracts/agent/tool-call-request.v1` / `tool-call-response.v1` | Mọi lần gọi tool |
| `contracts/agent/structured-case-output.v1` | Đầu ra cuối cùng cho analyst |
| `contracts/events/aml.agent.toolcall.v1` / `aml.agent.claim.v1` | Nhật ký audit |
| `contracts/canonical/evidence-item.v1` | Evidence ledger |

Runtime dùng LangGraph, Temporal hay tự viết đều được — kiến trúc mục 8.7 nói rõ đó là lựa chọn
triển khai. Điều bắt buộc: state bền vững, side effect idempotent, tiếp tục được sau lỗi.

---

## Những việc agent KHÔNG được làm

Danh sách này không phải khuyến nghị. Nó đã được cưỡng chế ở tầng contract, và mọi hiện thực phải
giữ nguyên:

| Cấm | Cưỡng chế ở đâu |
|---|---|
| Sửa dữ liệu giao dịch gốc | Không có tool ghi nào trong allowlist |
| Đóng băng / chặn tài khoản | `FREEZE_ACCOUNT` không nằm trong enum `recommended_actions` |
| Tự nộp STR | `propose_str_draft` chỉ tạo bản nháp; `is_draft` là `const: true` |
| Đọc nhãn ẩn / ground truth | Vai trò `fin07_agent` không có quyền trên schema `label` |
| Chạy SQL hoặc shell tuỳ ý | Không tồn tại tool `execute_sql`/`run_shell`/`call_any_api` |
| Vượt RBAC | `user_context` bắt buộc; quyền hiệu lực là giao của quyền người dùng và quyền tool |
| Khẳng định không có bằng chứng | `evidence_refs` có `minItems: 1` ở mọi claim |

Một tool mới thêm vào allowlist là **thay đổi contract cần review bảo mật**, không phải một PR tính
năng thường.

---

## Ba thứ dễ làm sai

**`snapshot_time` cố định cho cả lượt chạy.** Một lượt điều tra chạy hàng phút và có thể tạm dừng
hàng giờ chờ người duyệt. Nếu mỗi tool trả "dữ liệu mới nhất", các bằng chứng trong cùng một case sẽ
mô tả các thời điểm khác nhau và timeline dựng ra sẽ tự mâu thuẫn.

**Nội dung do người ngoài soạn là dữ liệu, không phải chỉ dẫn.** `transaction.purpose_text`, tài
liệu OSINT, nội dung tải về — tất cả phải được đánh dấu `untrusted_content` và không bao giờ được
phép đổi system policy hay quyền tool. Đây là kênh prompt injection trực tiếp từ bên ngoài ngân hàng.

**`NEEDS_HUMAN` là kết thúc bình thường, không phải lỗi.** Agent đề xuất, con người quyết định. Tối
ưu để giảm tỷ lệ `NEEDS_HUMAN` là tối ưu sai hướng — nó sẽ đẩy agent tới chỗ tự tin quá mức.

---

## Đo thế nào

Mục 8.10. Bốn nhóm quan trọng nhất khi mới bắt đầu:

- **Evidence**: claim-evidence precision, citation validity, tỷ lệ claim không nguồn.
- **Safety**: số lần gọi tool bị từ chối, vi phạm policy, tỷ lệ prompt injection thành công.
- **Giá trị**: số phút analyst tiết kiệm được, edit distance trên bản nháp, số đề xuất được chấp nhận.
- **Reasoning**: khả năng phát hiện mâu thuẫn, chất lượng của việc **từ chối kết luận** khi không đủ
  căn cứ.

Không đo "độ chính xác" của agent như một mô hình phân loại — agent không ra quyết định, nên nó
không có độ chính xác theo nghĩa đó.
