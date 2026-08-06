# CI/CD — cổng chặn merge và pipeline giao hàng

Gộp từ `docs/CI.md` và `docs/CICD.md`. Hai file cũ tách nhau vì lý do lịch sử, nhưng người đọc gần
như luôn cần cả hai cùng lúc.

| | GitHub Actions | Jenkins |
|---|---|---|
| Vai trò | **Cổng chặn merge** | **Pipeline giao hàng** |
| Chạy khi | Mọi pull request, push lên `main`/`develop` | Mọi nhánh và pull request |
| Làm gì | lint, kiểm thử, hợp đồng, build image, `compose up` trên máy sạch | thêm: triển khai staging, phê duyệt, triển khai production-like, kiểm tra khói, quay lui |
| File | `.github/workflows/ci.yml` | `Jenkinsfile` |

**Cả hai gọi cùng các script trong `ci/`.** Không có logic CI nào viết hai lần, nên hai hệ thống
không lệch nhau được — và máy cá nhân chạy đúng những script đó.

```
                 ci/lint.sh   ci/test.sh   ci/build-images.sh
                 ci/smoke.sh  ci/deploy.sh ci/apply-schema.sh
                        ▲            ▲              ▲
                        │            │              │
              GitHub Actions     Jenkins       Máy cá nhân
```

---

## 1. Vì sao hai hệ thống

**Vì sao Jenkins.** FIN-07 là hệ thống giám sát AML; tài liệu đóng dấu "Nội bộ — Hạn chế". Tổ chức
tài chính nhận bàn giao sẽ chạy pipeline trong mạng của họ, không đẩy mã nguồn và bí mật lên runner
của bên thứ ba. Pipeline Jenkins bàn giao được nguyên trạng.

**Vì sao vẫn giữ GitHub Actions.** Yêu cầu nghiệm thu là "PR không đạt CI thì không merge được".
Cơ chế đó là branch protection của GitHub và nó cần một status check của GitHub. Bắt Jenkins báo
trạng thái ngược về PR thì Jenkins phải phơi ra Internet — rủi ro không đáng đổi.

---

## 2. Các job của cổng chặn merge

| Job | Kiểm cái gì | Thời gian điển hình |
|---|---|---|
| `lint` | `ruff check` và `ruff format --check` | ~40 giây |
| `test` | pytest với PostgreSQL và Redis thật, kèm độ phủ. Bao gồm kiểm chứng hợp đồng dữ liệu (`tests/test_contracts/`) | ~1,5 phút |
| `web` | `tsc --noEmit` và `vite build` | ~1 phút |
| `images` | Build và đẩy image api/worker và web lên GHCR | ~2–3 phút (có cache) |
| `compose-smoke` | `docker compose up` trên máy sạch, mọi healthcheck phải xanh | ~1,5 phút |
| `ci` | Cổng tổng hợp, gom kết quả các job trên | ~5 giây |

Tổng thời gian tường ≈ **4–5 phút**. Mỗi job đặt `timeout-minutes: 8`.

Ba thứ giữ pipeline nhanh: cache pip theo `requirements-dev.txt`, cache npm theo
`web/package-lock.json`, cache lớp Docker (`type=gha`) tách scope từng image, và `compose-smoke`
**kéo** image mà `images` vừa đẩy thay vì build lại.

### Job `test` chạy gì

Kiểm thử tích hợp dùng PostgreSQL và Redis thật, không mock. Lý do: những ràng buộc quan trọng nhất
của FIN-07 nằm ở tầng cơ sở dữ liệu — nhật ký bất biến, phê duyệt ghi một lần, cách ly vai trò
agent. Mock một cơ sở dữ liệu rồi kiểm tra mock không chứng minh được gì.

1. Dựng service container `postgres:16-alpine` và `redis:7-alpine` (cổng động — runner của ban tổ
   chức đã có thứ gì đó nghe trên 5432).
2. Áp lược đồ bằng **chính** các file trong `db/init/`.
3. Nạp dữ liệu mẫu, chạy `--verify` hai lần và so vân tay: cùng seed phải cho cùng dữ liệu.
4. `pytest` toàn bộ, kèm báo cáo độ phủ tải lên artifact.

---

## 3. Image đẩy đi đâu

```
ghcr.io/<org>/<repo>/app:sha-<commit>      # api và worker
ghcr.io/<org>/<repo>/web:sha-<commit>      # console
```

Kèm tag di động: `pr-<số>` với pull request, hoặc tên nhánh với push.

```bash
APP_IMAGE=ghcr.io/<org>/<repo>/app:sha-<commit> \
WEB_IMAGE=ghcr.io/<org>/<repo>/web:sha-<commit> \
docker compose up -d --wait --no-build
```

PR từ fork chỉ có token chỉ đọc nên không đẩy được: `images` vẫn build để bắt lỗi Dockerfile, còn
`compose-smoke` bị bỏ qua.

---

## 4. Bật chặn merge — việc phải làm một lần trên GitHub

CI chạy đỏ **không** tự chặn merge. Phải bật branch protection, và đây là thao tác trên giao diện
GitHub, không nằm trong repo: `Settings → Branches → Add branch ruleset`.

| Mục | Giá trị |
|---|---|
| Target branches | `main`, `develop` |
| Require a pull request before merging | bật |
| Require status checks to pass | bật |
| Status check bắt buộc | **`CI`** — đúng một cái |
| Require branches to be up to date | bật |
| Block force pushes | bật |

```bash
gh api -X PUT repos/:owner/:repo/branches/develop/protection \
  -F required_status_checks[strict]=true \
  -f 'required_status_checks[contexts][]=CI' \
  -F enforce_admins=false \
  -F required_pull_request_reviews[required_approving_review_count]=1 \
  -F restrictions=null
```

Chỉ chọn **một** status check tên `CI` — job cổng gom kết quả mọi job khác. Thêm job mới thì chỉ cần
thêm vào `needs` của job `ci`, không phải vào GitHub sửa lại cấu hình.

> **Chưa bật.** Cho tới khi bật, CI đỏ vẫn merge được như thường.

---

## 5. Luồng giao hàng

```
  Nhánh feature  →  pull request
       │
       ▼  GitHub Actions — đỏ thì không merge được
       │  merge vào develop
       ▼  Jenkins: chất lượng → build → triển khai STAGING (tự động) → khói → hỏng thì QUAY LUI
       │  merge vào main
       ▼  Jenkins: ⏸ CHỜ NGƯỜI PHÊ DUYỆT (bắt buộc có lý do) → PRODUCTION-LIKE → khói → quay lui
```

Cổng phê duyệt không phải thủ tục hành chính. Nguyên tắc NT3 của dự án là con người quyết định cuối
cùng ở mọi đường dẫn có hậu quả. Jenkins bắt người phê duyệt nhập lý do, và lý do đó vào nhật ký
build — cùng tinh thần với việc hệ thống bắt MLRO nêu lý do khi duyệt hồ sơ nghi vấn.

---

## 6. Ba môi trường

| | Phát triển | Staging | Production-like |
|---|---|---|---|
| Dùng để | máy cá nhân | kiểm thử tích hợp, demo nội bộ | đánh giá cuối, nghiệm thu |
| Triển khai bởi | `docker compose up` | Jenkins, tự động khi merge `develop` | Jenkins, sau khi có người duyệt |
| Lớp phủ compose | không | `deploy/docker-compose.staging.yml` | `deploy/docker-compose.prodlike.yml` |
| PostgreSQL, Redis | mở cổng ra máy chủ | **không mở** | **không mở** |
| Image | build tại chỗ | chỉ kéo image đã qua kiểm thử | chỉ kéo image đã qua kiểm thử |
| `APP_ENV` | `development` | `staging` | `production` |
| Xoá dữ liệu | được | phải bấm `FORCE_RESEED` | **script từ chối** |

`APP_ENV=production` làm hàm `wipe()` trong `scripts/seed_data.py` từ chối chạy. Dữ liệu ở môi
trường nghiệm thu không bị xoá bằng một lệnh lỡ tay.

Không build tại chỗ ở staging và production-like, vì build tại chỗ nghĩa là thứ đang chạy không
phải thứ CI vừa kiểm.

---

## 7. Dựng Jenkins

Controller và agent đều dựng từ mã nguồn trong `jenkins/`. Không bấm qua giao diện.

```bash
cd jenkins
cp .env.example .env          # điền bí mật
docker compose up -d controller
# mở http://localhost:8080, đăng nhập bằng JENKINS_ADMIN_ID/PASSWORD

# lấy secret ở http://localhost:8080/computer/fin07-agent-1/
# điền vào JENKINS_AGENT_SECRET trong jenkins/.env
docker compose --profile agent up -d
```

**Agent phải chạy trên Linux.** Nó dùng `network_mode: host`, và đó không phải tuỳ chọn: agent build
image bằng Docker daemon của máy chủ, nên container mà pipeline dựng lên publish cổng ra máy chủ chứ
không ra mạng của agent. Không dùng mạng máy chủ thì bước kiểm tra khói gọi `localhost:8000` sẽ gọi
vào chính agent và luôn thất bại.

`jenkins/casc.yaml` là nguồn sự thật duy nhất: người dùng, phân quyền, credentials, node, job
multibranch. Sửa qua giao diện web thì lần khởi động lại tiếp theo ghi đè — đó là chủ ý. Controller
đặt `numExecutors: 0`: tiến trình đang giữ toàn bộ credentials không nên là tiến trình chạy mã đến
từ pull request.

### Credentials

Jenkins đọc bí mật từ biến môi trường qua JCasC. Không giá trị nào nằm trong repo.

| ID | Dùng ở đâu |
|---|---|
| `fin07-registry` | đẩy image lên GHCR |
| `fin07-github` | đọc mã nguồn, quét nhánh |
| `fin07-staging-*` (postgres, agent-db, google-api-key) | triển khai staging |
| `fin07-prodlike-*` (postgres, agent-db, google-api-key) | triển khai production-like |

Staging và production-like **không dùng chung mật khẩu**. Dùng chung thì việc tách hai môi trường
chỉ còn là hình thức.

---

## 8. Quay lui

`ci/deploy.sh` tự quay lui:

1. Đọc image đang chạy **trên máy đích** (không đọc từ workspace Jenkins — workspace bị xoá giữa các
   lượt build, máy đích thì luôn biết chính nó đang chạy gì).
2. Triển khai phiên bản mới, chờ mọi healthcheck xanh.
3. Chạy `ci/smoke.sh`.
4. Hỏng ở bước 2 hoặc 3 → triển khai lại image cũ, và build đỏ.

Healthcheck xanh mới chỉ nói tiến trình còn sống. Kiểm tra khói mới là thứ quyết định giữ hay quay
lui: nó đi qua đường dữ liệu thật và chứng minh chuỗi API → Redis → worker → PostgreSQL thông.

---

## 9. Chạy đúng những gì CI chạy, trước khi mở PR

```bash
make check                              # lint + test, tương đương job `lint` + `test`
docker compose up -d --build --wait     # tương đương compose-smoke
cd web && npm run typecheck && npm run build
```

Mọi script trong `ci/` chạy độc lập được — đây cũng là cách gỡ lỗi nhanh nhất khi pipeline đỏ:

```bash
./ci/lint.sh
./ci/test.sh                 # tự dựng PostgreSQL và Redis, chạy kiểm thử, dọn sạch
./ci/build-images.sh
./ci/smoke.sh
./ci/deploy.sh staging
```

---

## 10. Những chỗ chưa làm, nói rõ ra

- **Chưa bật branch protection** — mục 4. Chưa bật thì CI đỏ vẫn merge được.
- **Chưa có quét bảo mật image** (Trivy/Grype). Xem `docs/repository/DEPENDENCY_REPORT.md`.
- **Không có hạ tầng dưới dạng mã.** VPS thuê ngoài, dựng bằng tay. Pipeline triển khai lên máy chủ
  *đã tồn tại* qua `docker context`, không tự tạo ra máy chủ. Đây là quyết định, không phải chỗ bị
  bỏ sót — nhưng hệ quả là dựng lại máy chủ từ đầu không tái lập được từ repo.
- **Chưa có kênh thông báo khi build hỏng.** Khối `post { failure { } }` trong `Jenkinsfile` để
  trống có chủ ý: một webhook giả cắm sẵn mà không tới nơi còn tệ hơn không có thông báo.
- **Chưa có kiểm tra tải** và **chưa có sao lưu/diễn tập khôi phục**.
