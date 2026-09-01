# Worklog — FIN-07

> Ghi lại công việc theo ngày: ai làm gì, ra kết quả gì.
> Phần **Bàn giao** ở cuối file dành cho người bắt đầu sau — đọc phần đó trước.

---

## 2026-07-29

| Thành viên | Công việc | Trạng thái | Kết quả | Thời gian |
|---|---|---|---|---|
| Bảo | Dựng toàn bộ hệ thống bằng một lệnh `docker compose up` | ✅ Done | 5 dịch vụ + tác vụ migration, mọi healthcheck xanh | 4h |
| Bảo | Lược đồ cơ sở dữ liệu theo Hình 6 của ARC-001 | ✅ Done | `db/init/`, kèm ràng buộc bất biến ở tầng dữ liệu | — |
| Bảo | Script dữ liệu mẫu (lịch sử, đã loại bỏ) | 🗑 Removed | Thay bằng batch IBM AML LI-Small | — |
| Bảo | CI chặn merge trên mọi pull request | ✅ Done | `.github/workflows/ci.yml`, ~4–5 phút | 2h |
| Bảo | Pipeline CD đầy đủ bằng Jenkins | ✅ Done | `Jenkinsfile`, `ci/`, `deploy/`, `jenkins/` | 3h |
| Bảo | Tài liệu vận hành và bàn giao | ✅ Done | `docs/operations/README.md#runbook-dựng-và-vận-hành-fin-07-trên-máy-cá-nhân`, `docs/operations/README.md#cicd-cổng-chặn-merge-và-pipeline-giao-hàng` | — |

**Tổng kết ngày (đã cập nhật):** Hạ tầng chạy bằng Docker; dữ liệu demo ban đầu
đã được loại bỏ sau khi batch IBM AML LI-Small hoàn thành. Máy mới cần nạp
LI-Small theo runbook để có dữ liệu trên console.

---

# Bàn giao

## 1. Bắt đầu trong 5 phút

Chỉ cần Docker. Không cần Python, không cần Node, không cần tạo `.env`.

```bash
git clone <repo> && cd P-022
docker compose up
```

Xong. Mở:

- Console — <http://localhost:5173>
- API docs — <http://localhost:8000/docs>

Stack không tự tạo dữ liệu nghiệp vụ. Nạp batch IBM AML LI-Small theo runbook
trước khi kiểm tra các màn hình.

Đọc tiếp: [Runbook — dựng và vận hành FIN-07 trên máy cá nhân](docs/operations/README.md#runbook-dựng-và-vận-hành-fin-07-trên-máy-cá-nhân).

## 2. Ai sở hữu cái gì

Đây là phần quan trọng nhất của tài liệu này. Tôi đã viết một ít mã nằm trong
phần của các anh, để chứng minh hệ thống chạy thông đầu–cuối. **Toàn bộ chỗ đó
là chỗ trống, không phải thiết kế.** Xoá đi viết lại thoải mái.

### Hưng — Frontend

| Đường dẫn | Ai sở hữu | Ghi chú |
|---|---|---|
| `web/src/**` | **Hưng** | Tôi để tạm một bảng hàng đợi vụ việc và panel chi tiết. Cố ý làm xấu: bảng trần, không design system, để không ai nhầm đây là UI thật. Xoá sạch, viết lại theo wireframe epic E09. |
| `web/Dockerfile` | Bảo | Build 2 tầng, chạy non-root. Đổi cấu trúc thì báo trước. |
| `web/nginx.conf` | Bảo | Proxy `/api` và endpoint `/healthz`. |
| `web/vite.config.ts`, `tsconfig.json` | chung | Thêm plugin thì cứ thêm; đổi `outDir` thì báo, Dockerfile phụ thuộc vào nó. |

Bắt đầu:

```bash
docker compose up -d          # backend chạy nền
cd web && npm install && npm run dev
```

Vite proxy sẵn `/api` về `localhost:8000`, không phải cấu hình CORS gì thêm.

Một điều tôi đã làm đúng ngay từ khung và mong anh giữ: **điểm rủi ro không
bao giờ hiển thị một mình.** Chỗ nào hiện điểm thì hiện kèm các yếu tố đóng
góp. Đây là nguyên tắc NT7 của dự án, không phải ý thích của tôi — mỗi cảnh
báo phải giải thích được bằng tối thiểu ba yếu tố có giá trị số.

### Tin Tin — Backend

| Đường dẫn | Ai sở hữu | Ghi chú |
|---|---|---|
| `src/api/routes.py` | **Tin Tin** | Tôi thêm `/cases`, `/cases/{id}`, `/investigate`, `/queue` để kiểm tra khói có cái mà gọi. Viết lại theo thiết kế API thật. |
| `src/models/schemas.py` | **Tin Tin** | Như trên. |
| `src/worker/main.py` | **Tin Tin** + Hiển | Vòng lặp worker và nhịp tim là hạ tầng, giữ nguyên. Phần `HANDLERS` là chỗ cắm agent LangGraph vào. |
| `src/db/session.py` | Bảo | Kết nối và pool. |
| `src/main.py` — `/health`, `/health/ready` | Bảo | **Đừng đổi.** Healthcheck của container và pipeline triển khai đều dựa vào chúng. |
| `src/config.py` | chung | Thêm biến thì phải cập nhật cả `.env.example` và `.env.example`, nếu không CI đỏ (có kiểm thử đối chiếu ba nguồn). |
| `db/init/**` | Bảo | Đổi lược đồ thì báo — xem mục 4. |

Bắt đầu:

```bash
docker compose up -d postgres redis
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env      # đổi host trong DATABASE_URL thành localhost
make run                  # API, có --reload
make worker               # worker, cửa sổ khác
```

### Hiển — AI Engineer

| Đường dẫn | Ghi chú |
|---|---|
| `src/agents/**` | Của anh hoàn toàn. Hiện là mã mẫu của template. |
| `src/worker/main.py` → `HANDLERS` | Chỗ cắm agent điều tra vào worker. |
| Dữ liệu vận hành | Chỉ dùng IBM AML LI-Small; fixture demo lịch sử đã được loại bỏ. |
| Vai trò `fin07_agent` | Agent chỉ đọc được schema `agent`, **không** chạm được schema `label`. Không phải để làm khó — đó là cách chặn rò rỉ nhãn vào đặc trưng (RD1, mức Rất cao). Cần thêm trường thì thêm view vào `db/init/003_agent_readonly_role.sh` qua pull request. |

## 3. Quy ước làm việc

```
nhánh feature  →  pull request  →  develop  →  main
                       │              │          │
                  CI phải xanh    staging   production-like
                                  (tự động)  (cần người duyệt)
```

- Nhánh đặt tên `feat/<epic>-<mô tả>` hoặc `fix/<mô tả>`
- **Không đẩy thẳng lên `develop` hay `main`**
- Trước khi mở PR: `make check` (chạy đúng những gì CI chạy)
- CI đỏ thì sửa CI, đừng tìm cách đi vòng

## 4. Ba cái bẫy đã có người sập, để không sập lần nữa

**Sửa file trong `db/init/` mà không thấy tác dụng.** Script khởi tạo chỉ chạy
khi volume PostgreSQL còn rỗng. Volume đã có dữ liệu thì lần khởi động sau
container bỏ qua toàn bộ thư mục đó và **không nói gì cả**. Chạy `make db-reset`.

**Chạy `python scripts/...` ngoài Docker mà báo `No module named 'src'`.**
Đã xử lý trong `seed_data.py`. Viết script mới trong `scripts/` thì nhớ thêm
gốc repo vào `sys.path`, hoặc chạy bằng `python -m scripts.<tên>`.

**Đổi `WEB_PORT` mà quên `CORS_ORIGINS`.** Trình duyệt sẽ chặn mọi request và
lỗi hiện ra trông không liên quan gì tới cổng.

## 5. Những ràng buộc không được nới

Bốn thứ dưới đây bị PostgreSQL cưỡng chế, không phải quy ước trong mã. Có kiểm
thử tự động chứng minh chúng chặn thật. Nếu công việc của các anh đụng phải
chúng thì **hỏi trước**, đừng gỡ ràng buộc:

| Ràng buộc | Vì sao |
|---|---|
| `audit_log` và `evidence` chỉ ghi thêm | Vụ việc phải tái dựng được khi thanh tra hỏi |
| Phê duyệt ghi một lần, bắt buộc có lý do | Con người quyết định cuối cùng, và quyết định đó không sửa lại |
| Agent không đọc được schema `label` | Rò rỉ nhãn cho ra chỉ số đẹp giả tạo, không ai phát hiện tới lúc bảo vệ |
| Trạng thái vụ việc theo đúng máy trạng thái Hình 4 | Không có đường tắt nào tới xuất hồ sơ mà không qua người duyệt |

## 6. Việc còn tồn

| Việc | Ai | Ghi chú |
|---|---|---|
| Bật branch protection cho `main` và `develop` | Bảo | **Chưa làm.** CI đỏ vẫn merge được cho tới khi bật. [CI/CD — cổng chặn merge và pipeline giao hàng](docs/operations/README.md#cicd-cổng-chặn-merge-và-pipeline-giao-hàng) mục 5 |
| Thuê VPS và mua tên miền cho staging / production-like | Bảo | Pipeline triển khai đã có, máy chủ thì chưa. Dựng bằng tay, không dùng Terraform |
| Cắm kênh thông báo khi build hỏng | Bảo | Khối `post { failure }` trong `Jenkinsfile` đang để trống |
| Quét bảo mật image (Trivy/Grype) | Bảo | Nên có trước khi bàn giao |
| Kiểm tra tải theo mục tiêu ARC-001 mục 5.3 | Bảo | Sprint 5 |
| Nạp dataset IBM LI-Small thật | Hiển | Sprint 1, FIN-07-DAT-001 |

## 7. Đọc gì

| Tài liệu | Khi nào cần |
|---|---|
| [Runbook — dựng và vận hành FIN-07 trên máy cá nhân](docs/operations/README.md#runbook-dựng-và-vận-hành-fin-07-trên-máy-cá-nhân) | Dựng, vận hành, xử lý sự cố |
| [.env.example](.env.example) | Mọi biến môi trường |
| [CI/CD — cổng chặn merge và pipeline giao hàng](docs/operations/README.md#cicd-cổng-chặn-merge-và-pipeline-giao-hàng) | Cổng chặn merge, luồng giao hàng, ba môi trường, quay lui |
| [contracts/ingestion/README.md](contracts/ingestion/README.md) | Đường ống nạp dữ liệu: contract, lệnh, ba giao diện, bẫy khi chạy local |
| [Kiến trúc production — FIN-07 AML Level 1](docs/architecture/architecture.md#kiến-trúc-production-fin-07-aml-level-1) | Từ máy cá nhân tới production: hiện trạng, kiến trúc đích, khoảng cách |
| FIN-07-ARC-001 | Kiến trúc, quyết định thiết kế |
| FIN-07-DAT-001 | Nguồn dữ liệu, danh mục nhãn |
| FIN-07-BUS-001 | Nghiệp vụ AML, danh mục typology T01–T10 |
