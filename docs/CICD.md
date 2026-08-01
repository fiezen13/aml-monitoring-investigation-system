# CI/CD — thiết kế đầy đủ

## 1. Vì sao hai hệ thống, và ranh giới ở đâu

| | GitHub Actions | Jenkins |
|---|---|---|
| Vai trò | **Cổng chặn merge** | **Pipeline giao hàng** |
| Chạy khi | Mọi pull request | Mọi nhánh và pull request |
| Làm gì | lint, kiểm thử, build image, `compose up` trên máy sạch | thêm: triển khai staging, phê duyệt, triển khai production-like, kiểm tra khói, quay lui |
| Chạy ở đâu | Runner của GitHub | Máy tự host |
| File | `.github/workflows/ci.yml` | `Jenkinsfile` |

**Vì sao Jenkins chứ không phải GitLab CI.** Repo nằm trên GitHub trong tổ
chức của khoá học, không di chuyển được. Chạy GitLab CI cho một repo GitHub
cần tính năng "CI/CD for external repository", đó là bản trả phí, và phải
dựng mirror hai chiều. Nhiều việc, đổi lại không được gì.

**Vì sao Jenkins là lựa chọn đúng cho dự án này.** FIN-07 là hệ thống giám
sát AML; tài liệu đóng dấu "Nội bộ — Hạn chế". Tổ chức tài chính nhận bàn
giao sẽ chạy pipeline trong mạng của họ, không đẩy mã nguồn và bí mật lên
runner của bên thứ ba. Pipeline Jenkins bàn giao được nguyên trạng; pipeline
GitHub Actions thì họ phải viết lại từ đầu.

**Vì sao vẫn giữ GitHub Actions.** Yêu cầu nghiệm thu là "PR không đạt CI thì
không merge được". Cơ chế đó là branch protection của GitHub, và nó cần một
status check của GitHub. Bắt Jenkins báo trạng thái ngược về pull request thì
Jenkins phải nhận được webhook từ GitHub, tức là phải phơi ra Internet. Trong
5 tuần, đó là rủi ro không đáng đổi.

**Vì sao hai hệ thống không lệch nhau.** Cả hai đều gọi cùng các script trong
`ci/`. Không có logic CI nào viết hai lần. Sửa cách chạy kiểm thử thì sửa
`ci/test.sh`, cả hai hệ thống nhận thay đổi cùng lúc — và cả máy cá nhân cũng
vậy.

```
                 ci/lint.sh   ci/test.sh   ci/build-images.sh
                 ci/smoke.sh  ci/deploy.sh ci/apply-schema.sh
                        ▲            ▲              ▲
                        │            │              │
              GitHub Actions     Jenkins       Máy cá nhân
```

## 2. Luồng đầy đủ

```
  Nhánh feature
       │
       │  mở pull request
       ▼
  ┌──────────────────────────────────────────────┐
  │ GitHub Actions — cổng chặn merge             │
  │  lint · kiểm thử · giao diện · image · smoke │
  │  đỏ  → không merge được                      │
  └──────────────────────────────────────────────┘
       │  merge vào develop
       ▼
  ┌──────────────────────────────────────────────┐
  │ Jenkins — nhánh develop                      │
  │  kiểm tra chất lượng (song song ba việc)     │
  │  build và đẩy image                          │
  │  triển khai STAGING (tự động)                │
  │  kiểm tra khói → hỏng thì QUAY LUI           │
  └──────────────────────────────────────────────┘
       │  merge vào main
       ▼
  ┌──────────────────────────────────────────────┐
  │ Jenkins — nhánh main                         │
  │  kiểm tra chất lượng · build · đẩy image     │
  │  ⏸  CHỜ NGƯỜI PHÊ DUYỆT (bắt buộc có lý do)  │
  │  triển khai PRODUCTION-LIKE                  │
  │  kiểm tra khói → hỏng thì QUAY LUI           │
  └──────────────────────────────────────────────┘
```

Cổng phê duyệt không phải thủ tục hành chính. Nguyên tắc NT3 của dự án là con
người quyết định cuối cùng ở mọi đường dẫn có hậu quả. Đưa một phiên bản mới
vào môi trường mà hội đồng nghiệm thu nhìn vào là một đường dẫn như vậy.
Jenkins bắt người phê duyệt nhập lý do, và lý do đó vào nhật ký build — cùng
tinh thần với việc hệ thống bắt MLRO nêu lý do khi duyệt hồ sơ nghi vấn.

## 3. Dựng Jenkins

Controller và agent đều dựng từ mã nguồn trong `jenkins/`. Không bấm qua giao
diện: FIN-07-ARC-001 mục 7 ghi "không có môi trường nào được dựng bằng thao
tác tay", và controller cũng là một môi trường.

```bash
cd jenkins
cp .env.example .env          # điền bí mật
docker compose up -d controller
# mở http://localhost:8080, đăng nhập bằng JENKINS_ADMIN_ID/PASSWORD
```

Bootstrap agent có hai bước, vì secret của node chỉ tồn tại sau khi controller
lên:

```bash
# lấy secret ở http://localhost:8080/computer/fin07-agent-1/
# điền vào JENKINS_AGENT_SECRET trong jenkins/.env
docker compose --profile agent up -d
```

**Agent phải chạy trên Linux.** Nó dùng `network_mode: host`, và đó không phải
tuỳ chọn: agent build image bằng Docker daemon của máy chủ, nên container mà
pipeline dựng lên publish cổng ra máy chủ chứ không ra mạng của agent. Không
dùng mạng máy chủ thì bước kiểm tra khói gọi `localhost:8000` sẽ gọi vào chính
agent và luôn thất bại. Đây là cái bẫy tốn thời gian nhất khi chạy Docker qua
socket.

Công cụ agent phải có — `jenkins/agent/Dockerfile` cài sẵn, và bước đầu tiên
của `Jenkinsfile` kiểm tra lại:

`docker`, `docker compose` v2, `python3`, `node`, `npm`, `psql`, `jq`, `curl`,
`git`, `make`, `shellcheck`.

Hai chỗ này phải khớp nhau. Lệch thì pipeline đỏ ngay dòng đầu kèm thông báo
rõ ràng, chứ không đỏ giữa chừng vì một lệnh không tồn tại.

### Cấu hình bằng mã

`jenkins/casc.yaml` là nguồn sự thật duy nhất: người dùng, phân quyền,
credentials, node, và cả job multibranch. Sửa qua giao diện web thì lần khởi
động lại tiếp theo ghi đè — đó là chủ ý.

Controller đặt `numExecutors: 0`. Việc build đi xuống agent: tiến trình đang
giữ toàn bộ credentials của mọi môi trường không nên là tiến trình chạy mã đến
từ pull request.

## 4. Credentials

Jenkins đọc bí mật từ biến môi trường qua JCasC. Không giá trị nào nằm trong
repo.

| ID | Kiểu | Dùng ở đâu |
|---|---|---|
| `fin07-registry` | username + password | đẩy image lên GHCR |
| `fin07-github` | username + token | đọc mã nguồn, quét nhánh |
| `fin07-staging-postgres-password` | secret text | triển khai staging |
| `fin07-staging-agent-db-password` | secret text | triển khai staging |
| `fin07-staging-google-api-key` | secret text | triển khai staging |
| `fin07-prodlike-postgres-password` | secret text | triển khai production-like |
| `fin07-prodlike-agent-db-password` | secret text | triển khai production-like |
| `fin07-prodlike-google-api-key` | secret text | triển khai production-like |

Staging và production-like **không dùng chung mật khẩu**. Dùng chung thì việc
tách hai môi trường chỉ còn là hình thức.

Khi bàn giao cho tổ chức thật, thay `jenkins/.env` bằng kho bí mật của họ
(Vault, AWS Secrets Manager, hoặc tương đương). JCasC đọc biến môi trường nên
chỉ cần đổi nguồn tiêm biến, không phải sửa `casc.yaml`.

## 5. Ba môi trường

Theo FIN-07-ARC-001 mục 7.

| | Phát triển | Staging | Production-like |
|---|---|---|---|
| Dùng để | máy cá nhân | kiểm thử tích hợp, demo nội bộ | đánh giá cuối, nghiệm thu |
| Triển khai bởi | `docker compose up` | Jenkins, tự động khi merge vào `develop` | Jenkins, sau khi có người duyệt |
| Lớp phủ compose | không | `deploy/docker-compose.staging.yml` | `deploy/docker-compose.prodlike.yml` |
| PostgreSQL, Redis | mở cổng ra máy chủ | **không mở** | **không mở** |
| Image | build tại chỗ | chỉ kéo image đã qua kiểm thử | chỉ kéo image đã qua kiểm thử |
| `APP_ENV` | `development` | `staging` | `production` |
| Giới hạn tài nguyên | không | không | có |
| Xoay vòng log | không | không | có |
| Xoá dữ liệu | được | được, phải bấm `FORCE_RESEED` | **script từ chối** |

Điểm cuối cùng đáng nói rõ: `APP_ENV=production` làm hàm `wipe()` trong
`scripts/seed_data.py` từ chối chạy. Dữ liệu ở môi trường nghiệm thu không bị
xoá bằng một lệnh lỡ tay.

Không build tại chỗ ở staging và production-like, vì build tại chỗ nghĩa là
thứ đang chạy không phải thứ CI vừa kiểm.

## 6. Quay lui

`ci/deploy.sh` tự quay lui. Trình tự:

1. Đọc image đang chạy **trên máy đích** (không đọc từ workspace Jenkins —
   workspace bị xoá giữa các lượt build, máy đích thì luôn biết chính nó đang
   chạy gì)
2. Triển khai phiên bản mới, chờ mọi healthcheck xanh
3. Chạy `ci/smoke.sh`
4. Hỏng ở bước 2 hoặc 3 → triển khai lại image cũ, và build đỏ

Healthcheck xanh mới chỉ nói tiến trình còn sống. Kiểm tra khói mới là thứ
quyết định giữ hay quay lui: nó đi qua đường dữ liệu thật, và mắt xích cuối
chứng minh chuỗi API → Redis → worker → PostgreSQL thông.

Lần triển khai đầu tiên không có gì để quay lui về. Script nói rõ điều đó
trong log thay vì im lặng.

## 7. Việc còn phải làm bằng tay

Ba việc, không nằm trong repo được:

1. **Bật branch protection** cho `main` và `develop`, chọn status check `CI`.
   Xem [CI.md](CI.md) mục 5. Chưa bật thì CI đỏ vẫn merge được như thường.
2. **Dựng máy chủ staging và production-like**, tạo `docker context` trỏ tới
   chúng, đặt tên `fin07-staging` và `fin07-prodlike`. Máy chủ là VPS thuê
   ngoài, dựng bằng tay — xem mục 8.
3. **Cắm kênh thông báo** khi build hỏng. Khối `post { failure { } }` trong
   `Jenkinsfile` đang để trống có chủ ý: một webhook giả cắm sẵn mà không tới
   nơi còn tệ hơn không có thông báo, vì người ta tưởng là có.

## 8. Những chỗ chưa làm, nói rõ ra

- **Không có hạ tầng dưới dạng mã.** ARC-001 mục 6 liệt kê Terraform trong
  ngăn xếp và mục 7 nói staging "dựng bằng Terraform". Dự án đã chọn hướng
  khác: **VPS thuê ngoài kèm tên miền riêng**, dựng bằng tay. Pipeline triển
  khai lên máy chủ *đã tồn tại* qua `docker context`, chứ không tự tạo ra máy
  chủ. Đây là quyết định, không phải chỗ bị bỏ sót.

  Hệ quả cần biết: dựng lại máy chủ từ đầu là việc làm tay và không tái lập
  được từ repo. Ai dựng máy phải ghi lại các bước ở đâu đó — nếu không, kiến
  thức đó chỉ nằm trong đầu một người.
- **Kiểm tra tải.** Mục tiêu hiệu năng ở ARC-001 mục 5.3 (agent ≤ 3 phút, đồ
  thị 5.000 nút ≤ 5 giây, 50 cảnh báo ≤ 500 ms) chưa có bài kiểm tra tự động
  nào. Thuộc Sprint 5.
- **Sao lưu và diễn tập khôi phục.** Yêu cầu của môi trường production-like,
  chưa có job nào.
- **Quét bảo mật image.** Nên thêm Trivy hoặc Grype vào giai đoạn build trước
  khi bàn giao.

## 9. Chạy thử pipeline không cần Jenkins

Mọi script trong `ci/` chạy độc lập được:

```bash
./ci/lint.sh                 # lint và định dạng
./ci/test.sh                 # tự dựng PostgreSQL và Redis, chạy kiểm thử, dọn sạch
./ci/build-images.sh         # build image, không đẩy
./ci/smoke.sh                # kiểm tra khói vào stack đang chạy
./ci/deploy.sh staging       # triển khai lên máy này (chưa đặt docker context)
```

Đây cũng là cách gỡ lỗi nhanh nhất khi pipeline đỏ: chạy đúng script đó ở máy
mình, không cần đợi vòng lặp Jenkins.
