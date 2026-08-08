# Đóng góp vào FIN-07

Quy ước làm việc thật của team, trích từ `WORKLOG.md` — xem file đó để biết chi tiết bàn giao và ai
sở hữu module nào.

## Quy trình

```
nhánh feature  →  pull request  →  develop  →  main
                       │              │          │
                  CI phải xanh    staging   production-like
                                  (tự động)  (cần người duyệt)
```

- Nhánh đặt tên `feat/<epic>-<mô tả>` hoặc `fix/<mô tả>`.
- **Không đẩy thẳng lên `develop` hay `main`.**
- Trước khi mở PR: `make check` (tương đương job `lint` + `test` của CI).
- CI đỏ thì sửa nguyên nhân, đừng tìm cách đi vòng (`--no-verify`, disable test, v.v.).
- Dùng template PR có sẵn (`.github/pull_request_template.md`) — điền đủ mục contract impact và
  migration impact nếu có, đây là hai mục hay bị bỏ trống nhất và gây sự cố nhiều nhất.

## Ranh giới sở hữu module

Xem `.github/CODEOWNERS` để biết ai review phần nào. Bốn ràng buộc dưới đây bị PostgreSQL cưỡng chế
ở tầng dữ liệu (không phải quy ước code) — đụng vào chúng thì hỏi trước, đừng tìm cách gỡ:

| Ràng buộc | Vì sao |
|---|---|
| `audit_log` và `evidence` chỉ ghi thêm | Vụ việc phải tái dựng được khi thanh tra hỏi |
| Phê duyệt ghi một lần, bắt buộc có lý do | Con người quyết định cuối cùng, quyết định đó không sửa lại |
| Agent không đọc được schema `label` | Rò rỉ nhãn cho ra chỉ số đẹp giả tạo |
| Trạng thái vụ việc theo đúng máy trạng thái (`src/domain.py`) | Không có đường tắt tới xuất hồ sơ mà không qua người duyệt |

## Trước khi mở PR

```bash
make check                              # lint + test, đúng những gì CI job `lint`+`test` chạy
docker compose up -d --build --wait     # tương đương job compose-smoke
cd web && npm run typecheck && npm run build
```

## Đổi cấu hình / biến môi trường

Thêm một trường vào `src/config.py` hoặc `src/aml/config.py` mà quên cập nhật `.env.example` và
`.env.example` sẽ làm `tests/test_config_documented.py` đỏ — đây là chủ đích, không phải bug
của test. Cập nhật cả ba nguồn cùng lúc.

## Đổi lược đồ cơ sở dữ liệu

Không dùng Alembic. Thêm file `db/init/00N_mô_tả.sql` mới (số tăng dần), báo trước cho Bảo (owner
của `db/init/`), và chạy `make migrate` để áp lên cơ sở dữ liệu đã có dữ liệu — `db/init/` chỉ tự
chạy khi volume PostgreSQL rỗng.

## Đổi hợp đồng sự kiện AML

Không đổi `contracts/ingestion/aml-transaction-v1.schema.json` một cách phá vỡ tương thích. Bump
`schema_version`, thêm test tương thích, và cập nhật cả ba nơi đọc field set: `TransactionValidator`
(Java), `TransactionJsonParser.KNOWN_FIELDS` (Java), `AmlTransactionEvent` (Python) — ba nơi này
hiện không đồng bộ tự động, đổi một nơi mà quên hai nơi kia sẽ không bị CI bắt lỗi.

## Đọc thêm

- [docs/operations/RUNBOOK.md](docs/operations/RUNBOOK.md) — dựng và vận hành
- [.env.example](.env.example) — mọi biến môi trường
- [docs/operations/CICD.md](docs/operations/CICD.md) — cổng chặn merge chạy gì
- [docs/operations/CICD.md](docs/operations/CICD.md) — luồng giao hàng đầy đủ
- [docs/architecture/](docs/architecture/) — kiến trúc hệ thống
