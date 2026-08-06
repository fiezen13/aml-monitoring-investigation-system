# Repository Standardization Report — v1

**Ngày:** 2026-08-06
**Nhánh:** `chore/repository-standardization-v1` (từ `develop`)
**Phạm vi thực hiện:** Audit đầy đủ + hygiene cấp repo. **Không** tổ chức lại `src/`, `web/`,
`flink/`, không tạo `apps/`/`services/`/`ml/` — xem lý do ở
[`docs/adr/0001-repository-standardization-scope.md`](../adr/0001-repository-standardization-scope.md),
quyết định đã được Bảo xác nhận trực tiếp trong phiên làm việc này.

## 1. Cây thư mục cuối cùng

Không đổi so với trước — xem [`REPOSITORY_AUDIT.md`](REPOSITORY_AUDIT.md) mục 1 cho cây đầy đủ.
Phần thêm mới nằm ở gốc và trong `docs/`:

```
.
├── .editorconfig                 [MỚI]
├── .gitattributes                [MỚI]
├── .github/
│   ├── CODEOWNERS                [MỚI]
│   └── pull_request_template.md  [MỚI]
├── CONTRIBUTING.md               [MỚI]
├── SECURITY.md                   [MỚI]
├── LICENSE                       [MỚI]
├── docs/
│   ├── adr/
│   │   └── 0001-repository-standardization-scope.md   [MỚI]
│   ├── repository/
│   │   ├── REPOSITORY_AUDIT.md                         [MỚI]
│   │   ├── DEPENDENCY_REPORT.md                         [MỚI]
│   │   └── REPOSITORY_STANDARDIZATION_REPORT.md (file này) [MỚI]
│   └── ENVIRONMENT.md            [SỬA — thêm 7 biến Flink còn thiếu]
└── web/.env.example              [SỬA — sửa comment lạc hậu về "mock data"]
```

## 2. File đã di chuyển

Không có — phạm vi lần này không `git mv` bất kỳ file mã nguồn nào.

## 3. File đã xoá và lý do

Không có. Ba ứng viên không chắc chắn (`JOURNAL.md`, `web/vercel.json`,
`.github/modernize/java-upgrade/`) được giữ nguyên theo quyết định của Bảo trong phiên làm việc này
— xem `REPOSITORY_AUDIT.md` mục 13–14.

## 4. File/thư mục legacy được giữ lại và vì sao

| Đường dẫn | Vì sao giữ |
|---|---|
| `README_boilerplate.md` | Template README dùng chung cho các đội AI20K khác, không phải tài liệu của FIN-07 — không thuộc phạm vi cleanup của repo này |
| `docs/guide/` (10 chương giáo trình) | Tài liệu chương trình học AI20K, không phải tài liệu kiến trúc FIN-07 |
| `.agents/`, `.ai-log/`, `.claude/`, `.codex/`, `.cursor/`, `.gemini/`, `.github/hooks/` | Hạ tầng AI-usage-logging **bắt buộc của chương trình** (deliverable #4 — AI Logs). Xoá sẽ vi phạm yêu cầu nộp bài, không phải rác kỹ thuật |
| `JOURNAL.md` | Deliverable #8 (Development Journal) của BTC, dù hiện còn trống — giữ theo quyết định của Bảo |
| `web/vercel.json` | Giữ theo quyết định của Bảo, chưa xác nhận rõ còn dùng hay không |
| `.github/modernize/java-upgrade/` | Giữ theo quyết định của Bảo, artifact không gây hại (không track thêm gì) |
| `README.md` (phần boilerplate ở cuối) | Không sửa trong lần này — nêu ở audit mục 12/19 là nguồn nhầm lẫn, nhưng viết lại README là việc có chủ đích riêng, chưa nằm trong phạm vi hygiene đã thống nhất |

## 5. Lệnh bootstrap repository

```bash
git clone https://github.com/AI20K-Build-Phase-Cohort-3/P-022.git
cd P-022
docker compose up -d --wait
```

Không cần `.env`, không cần cài Python/Node trước — xem `docs/RUNBOOK.md`.

## 6. Lệnh chạy từng thành phần

```bash
make up            # toàn bộ stack chính (postgres, redis, api, worker, web)
make aml-up         # thêm Kafka + HDFS + Flink (profile aml, ~4GB RAM)
make abm             # sinh case ABM VN-CA-03
make run / make worker   # chạy api/worker ngoài Docker (cần venv)
cd web && npm run dev    # frontend hot-reload
```

## 7. Lệnh format/lint/test

```bash
make check          # ruff check + ruff format --check + pytest (đúng CI job lint+test)
make format          # ruff format
make lint             # ruff check
cd web && npm run typecheck && npm run build
cd flink/aml-ingestion && mvn -B test    # kiểm thử Java
```

Đã xác minh trong phiên làm việc này: `ruff check`/`ruff format --check` xanh, và
`tests/test_config_documented.py` (test bị ảnh hưởng trực tiếp bởi việc sửa `docs/ENVIRONMENT.md`)
pass đầy đủ (76/76 tham số hoá).

## 8. Tóm tắt CI

Không đổi. Hai hệ thống: GitHub Actions (`ci.yml`, cổng chặn merge, 5 job:
lint/test/web/images/compose-smoke) + Jenkins (`Jenkinsfile`, giao hàng staging/production-like).
Xem `docs/CI.md`/`docs/CICD.md`. **Chưa bật branch protection** — vẫn là việc tồn đọng đã ghi nhận
từ trước, không thuộc phạm vi lần chuẩn hoá này (cần thao tác tay trên GitHub UI/API).

## 9. Nợ kỹ thuật còn lại

Xem đầy đủ ở `REPOSITORY_AUDIT.md`. Tóm tắt các mục có giá trị hành động nhất:

1. CODEOWNERS còn 2 dòng `TODO` chờ Bảo xác nhận GitHub username của Tin Tin và Hiển.
2. `src/api/fc_routes.py` — 14 endpoint không có auth (chấp nhận được vì chỉ đọc dữ liệu tổng hợp,
   nhưng nên chuẩn hoá cùng cơ chế với `routes.py`).
3. `docs/demo_data_contract.md` mô tả một schema giao dịch khác với schema thật
   (`schemas/aml-transaction-v1.schema.json`) — tài liệu này có vẻ là đề xuất/aspirational nhưng
   không được đánh dấu rõ như vậy (khác với phần "Cảnh báo"/"bằng chứng" trong cùng file, vốn có ghi
   chú "chưa có trong pipeline"). Cần Bảo xác nhận và sửa lại phần transaction cho nhất quán.
4. `npm audit fix` chưa chạy thật (chỉ dry-run trong audit) — 2 lỗ hổng moderate ở
   `react-router`/`react-router-dom`, fix nằm trong semver hiện tại.
5. Chưa có quét lỗ hổng image (Trivy/Grype) trong CI — xem `DEPENDENCY_REPORT.md` mục 5.
6. Chưa bật branch protection cho `main`/`develop`.
7. `JOURNAL.md` còn trống hoàn toàn dù chương trình đã chạy nhiều tuần (theo `WORKLOG.md`).

## 10. Thay đổi phá vỡ tương thích (breaking changes)

Không có. Lần chuẩn hoá này không đổi API, không đổi event schema, không đổi lược đồ DB, không đổi
biến môi trường bắt buộc — chỉ thêm tài liệu/hygiene và bổ sung mô tả cho các biến môi trường Flink
đã tồn tại từ trước (không đổi giá trị mặc định nào).

## 11. Hướng dẫn rollback

Toàn bộ thay đổi nằm trên nhánh `chore/repository-standardization-v1`, chưa merge vào `develop`.

```bash
git checkout develop
git branch -D chore/repository-standardization-v1   # nếu muốn bỏ hẳn nhánh
```

Nếu đã merge một phần vào `develop`, revert từng commit riêng lẻ (xem mục 12 — mỗi hạng mục là một
commit độc lập, có thể revert không ảnh hưởng các phần khác vì không có phụ thuộc chéo giữa chúng).

## 12. Danh sách commit trong PR này

1. `docs: add repository audit and dependency report`
2. `chore: add repository hygiene files (CODEOWNERS, PR template, CONTRIBUTING, SECURITY, LICENSE, editorconfig, gitattributes)`
3. `docs: add ADR-0001 on repository standardization scope`
4. `docs: document missing Flink env vars and fix stale frontend env comment`
</content>
