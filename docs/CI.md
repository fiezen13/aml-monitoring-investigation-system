# CI — pipeline chạy trên mỗi pull request

Cấu hình: [`.github/workflows/ci.yml`](../.github/workflows/ci.yml)

## 1. Chạy khi nào

| Sự kiện | Chạy |
|---|---|
| Mở hoặc cập nhật **bất kỳ** pull request nào | có |
| Đẩy lên `main` hoặc `develop` | có |
| Bấm tay (`workflow_dispatch`) | có |

Chú ý "bất kỳ pull request nào", không giới hạn PR vào `main`: nhánh feature
gộp vào `develop` cũng phải qua cùng một cổng. Cấu hình cũ chỉ bắt PR vào
`main`, tức là phần lớn PR thực tế của nhóm không bị kiểm tra gì.

Đẩy commit mới lên một PR sẽ huỷ lượt chạy đang dở của PR đó
(`cancel-in-progress`).

## 2. Các job

Năm job đầu chạy song song hết mức có thể; `compose-smoke` phải chờ `images`.

| Job | Kiểm cái gì | Thời gian điển hình |
|---|---|---|
| `lint` | `ruff check` và `ruff format --check` | ~40 giây |
| `test` | pytest với PostgreSQL và Redis thật, kèm độ phủ | ~1,5 phút |
| `web` | `tsc --noEmit` và `vite build` | ~1 phút |
| `images` | Build và đẩy image api/worker và web lên GHCR | ~2–3 phút (có cache) |
| `compose-smoke` | `docker compose up` trên máy sạch, mọi healthcheck phải xanh | ~1,5 phút |
| `ci` | Cổng tổng hợp, gom kết quả năm job trên | ~5 giây |

Tổng thời gian tường ≈ `images` + `compose-smoke` ≈ **4–5 phút**, dưới mức
cam kết 8 phút. Mỗi job đặt `timeout-minutes: 8` nên một job treo sẽ bị cắt
chứ không chiếm runner vô hạn.

Ba thứ giữ cho pipeline nhanh:

1. Cache pip theo `requirements-dev.txt`, cache npm theo `web/package-lock.json`.
2. Cache lớp Docker trên GitHub Actions cache (`type=gha`), tách scope cho
   từng image. Lớp cài phụ thuộc chỉ build lại khi file requirements đổi.
3. `compose-smoke` **kéo** image mà `images` vừa đẩy thay vì build lại — đó là
   lý do `APP_IMAGE` và `WEB_IMAGE` là biến chứ không viết cứng trong
   `docker-compose.yml`.

## 3. Job `test` chạy gì

Kiểm thử tích hợp dùng PostgreSQL và Redis thật, không dùng mock. Lý do đơn
giản: những ràng buộc quan trọng nhất của FIN-07 nằm ở tầng cơ sở dữ liệu —
nhật ký bất biến, phê duyệt ghi một lần, cách ly vai trò agent. Mock một cơ
sở dữ liệu rồi kiểm tra mock không chứng minh được gì về ràng buộc thật.

Trình tự:

1. Dựng service container `postgres:16-alpine` và `redis:7-alpine`.
2. Áp lược đồ bằng **chính** các file trong `db/init/` — cùng nguồn với
   `docker compose`, không có bản sao thứ hai để lệch nhau theo thời gian.
3. Nạp dữ liệu mẫu.
4. Chạy `--verify` hai lần và so vân tay: cùng seed phải cho cùng dữ liệu
   (ND5). Lệch là có nguồn ngẫu nhiên chưa cố định.
5. `pytest` toàn bộ, kèm báo cáo độ phủ tải lên artifact.

## 4. Image đẩy đi đâu

GitHub Container Registry:

```
ghcr.io/<org>/<repo>/app:sha-<commit>      # api và worker
ghcr.io/<org>/<repo>/web:sha-<commit>      # console
```

Kèm một tag di động: `pr-<số>` với pull request, hoặc tên nhánh với push.

Kéo về chạy thử một commit cụ thể:

```bash
APP_IMAGE=ghcr.io/<org>/<repo>/app:sha-<commit> \
WEB_IMAGE=ghcr.io/<org>/<repo>/web:sha-<commit> \
docker compose up -d --wait --no-build
```

PR từ fork chỉ có token chỉ đọc nên không đẩy được: job `images` vẫn build để
bắt lỗi Dockerfile, còn `compose-smoke` bị bỏ qua. Nhóm làm việc trên nhánh
trong cùng repo nên trường hợp này gần như không xảy ra.

## 5. Bật chặn merge — việc phải làm một lần trên GitHub

CI chạy đỏ **không** tự chặn merge. Phải bật branch protection, và đây là
thao tác trên giao diện GitHub, không nằm trong repo:

`Settings → Branches → Add branch ruleset`

| Mục | Giá trị |
|---|---|
| Target branches | `main`, `develop` |
| Require a pull request before merging | bật |
| Require status checks to pass | bật |
| Status check bắt buộc | **`CI`** — đúng một cái |
| Require branches to be up to date | bật |
| Block force pushes | bật |

Bằng `gh` nếu tiện hơn:

```bash
gh api -X PUT repos/:owner/:repo/branches/develop/protection \
  -F required_status_checks[strict]=true \
  -f 'required_status_checks[contexts][]=CI' \
  -F enforce_admins=false \
  -F required_pull_request_reviews[required_approving_review_count]=1 \
  -F restrictions=null
```

Chỉ chọn **một** status check tên `CI`. Đó là job cổng gom kết quả của tất cả
job khác. Thêm job mới vào workflow thì chỉ cần thêm nó vào `needs` của job
`ci` — không phải vào GitHub sửa lại cấu hình lần nữa, và cũng không có
chuyện quên sửa rồi tưởng đang được bảo vệ.

## 6. Chạy đúng những gì CI chạy, trước khi mở PR

```bash
make check
```

Tương đương job `lint` cộng `test`. Hai job còn lại cần Docker:

```bash
docker compose up -d --build --wait   # tương đương compose-smoke
cd web && npm run typecheck && npm run build
```
