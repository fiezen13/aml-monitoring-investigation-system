## Mục đích

<!-- Vấn đề gì được giải quyết, hoặc tính năng gì được thêm. Liên kết issue/Jira nếu có. -->

**Jira/issue:**

## Thành phần bị ảnh hưởng

<!-- Đánh dấu tất cả thành phần mà PR này chạm vào. -->

- [ ] `src/api` — backend API
- [ ] `src/agents` — AI agent
- [ ] `src/worker` — worker nền
- [ ] `db/init` — lược đồ cơ sở dữ liệu
- [ ] `web/` — frontend
- [ ] `flink/aml-ingestion`, `src/aml` — luồng nạp dữ liệu Kafka → Flink → HDFS
- [ ] `schemas/` — hợp đồng sự kiện/dữ liệu
- [ ] `ci/`, `.github/workflows`, `Jenkinsfile` — CI/CD
- [ ] `docker-compose.yml`, `deploy/`, `Dockerfile*` — hạ tầng/triển khai
- [ ] Tài liệu (`docs/`)

## Ảnh hưởng tới contract

<!-- Có đổi event schema (schemas/aml-transaction-v1.schema.json), API response shape,
     hay bảng trong db/init/ không? Nếu có, mô tả và trỏ tới kế hoạch migration. -->

- [ ] Không đổi contract nào
- [ ] Có đổi — mô tả bên dưới, kèm kế hoạch tương thích ngược

## Ảnh hưởng migration

<!-- Có cần chạy `make migrate` / thêm file db/init/00N mới không? Có cần đổi biến môi trường không
     (nhớ cập nhật .env.example và docs/ENVIRONMENT.md nếu có)? -->

## Kiểm thử đã chạy

- [ ] `make check` (lint + test) chạy xanh cục bộ
- [ ] `cd web && npm run typecheck && npm run build`
- [ ] Kiểm thử thủ công (mô tả bên dưới, kèm ảnh chụp nếu là UI)

## Ảnh chụp màn hình (nếu đổi giao diện)

## Ảnh hưởng bảo mật/dữ liệu

<!-- Có endpoint mới không có auth? Có bảng/field chứa dữ liệu nhạy cảm mới? Có đổi quyền
     truy cập schema `label`/`fc_gt` không? -->

## Kế hoạch rollback

<!-- Nếu PR này gây sự cố sau khi merge, cách quay lui nhanh nhất là gì? -->

## Checklist

- [ ] Không có dataset, model binary, hay credential nào bị commit
- [ ] Không có file sinh ra (`.pytest_cache`, `coverage.xml`, `node_modules`, checkpoint Flink, v.v.) bị commit
- [ ] `.env.example` và `docs/ENVIRONMENT.md` đã cập nhật nếu có biến môi trường mới
</content>
