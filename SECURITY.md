# Security Policy — FIN-07

FIN-07 là hệ thống demo/PoC cho chương trình AI20K Build Phase, mô phỏng một console giám sát AML
ngân hàng. Toàn bộ dữ liệu trong stack mặc định (`docker compose up`) là dữ liệu tổng hợp
(`scripts/seed_data.py`, `scripts/abm_generate.py`) — không có khách hàng thật, không có danh sách
trừng phạt thật. Xem tài liệu kiến trúc trong `docs/architecture/` mục 8 để biết
đầy đủ các biện pháp bảo mật đã hiện thực.

## Báo cáo lỗ hổng

Trong phạm vi chương trình học, báo lỗ hổng trực tiếp cho Bảo (xem `.github/CODEOWNERS`) qua kênh
riêng tư (không mở public issue cho lỗ hổng chưa vá). Nêu rõ:

- Bước tái hiện.
- Thành phần bị ảnh hưởng (`src/api`, `web/`, `flink/aml-ingestion`, v.v.).
- Mức độ ảnh hưởng ước tính (đọc dữ liệu tổng hợp vs. leo quyền vs. RCE).

## Nguyên tắc bảo mật đang áp dụng

- **Bí mật:** không giá trị thật nào nằm trong repo. `.env` nằm trong `.gitignore`, `.env.example`
  chỉ chứa placeholder (ngoại lệ đã biết: `AI_LOG_API_KEY` — xem
  [`docs/repository/REPOSITORY_AUDIT.md`](docs/repository/REPOSITORY_AUDIT.md) mục 16–17, khoá này
  do giảng viên cung cấp dùng chung cho toàn khoá học, không phải bí mật của riêng FIN-07, nhưng vẫn
  cần Bảo xác nhận và cân nhắc xoay vòng).
- **Kiểm tra đầu vào:** Pydantic ở mọi endpoint FastAPI.
- **Phân quyền:** 5 vai trò (`compliance_officer`, `mlro`, `auditor`, `admin`, `analyst`), kiểm tra
  role inline theo từng endpoint ghi ở `src/api/routes.py`. Router `src/api/fc_routes.py` (đọc dữ
  liệu World Monitor/Financial City) hiện **không có auth** — chấp nhận được vì chỉ đọc dữ liệu tổng
  hợp, nhưng cần chuẩn hoá trước khi hệ thống này xử lý dữ liệu thật.
- **Nhật ký bất biến:** trigger PostgreSQL chặn sửa/xoá `audit_log`, `evidence`, và giới hạn
  `approval` chỉ quyết định một lần (`db/init/002_audit_immutability.sql`).
- **Cách ly agent:** vai trò `fin07_agent` chỉ đọc qua view trong schema `agent`, không đọc được
  schema `label` hay bảng gốc (`db/init/003_agent_readonly_role.sh`).
- **Nội dung người dùng nhập:** `transaction.remarks` luôn được xử lý như dữ liệu, không bao giờ
  diễn giải như chỉ dẫn cho agent/LLM.
- **AI Agent:** hiện là khung mẫu chưa hiện thực (`src/agents/`) — không có lời gọi LLM, không có
  quyền truy cập DB trực tiếp, không có khả năng đóng băng tài khoản hay nộp SAR. Khi hiện thực
  agent thật, các ràng buộc bắt buộc: không sửa transaction gốc, không tự đóng băng tài khoản, không
  tự nộp STR/SAR, không đọc `fc_gt` (ground truth ẩn), không truy cập DB/SQL tuỳ ý ngoài vai trò
  `fin07_agent`, không vượt RBAC. Xem `docs/architecture/` mục 4.

## Chưa hoàn thiện (biết trước, chưa phải bị bỏ sót)

- Chưa có quét lỗ hổng image tự động trong CI (Trivy/Grype) — xem
  [`docs/repository/DEPENDENCY_REPORT.md`](docs/repository/DEPENDENCY_REPORT.md).
- Chưa bật branch protection trên GitHub cho `main`/`develop` — xem `docs/operations/CICD.md` mục 5.
- Staging/production-like không mở cổng PostgreSQL/Redis ra ngoài, chỉ Caddy mở cổng ra Internet ở
  môi trường VM (`docs/operations/DEPLOY_VM.md`) — môi trường phát triển mặc định thì mở cổng ra máy chủ để
  tiện gỡ lỗi, có chủ đích, không dùng cho dữ liệu thật.
