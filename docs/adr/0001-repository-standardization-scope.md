# ADR-0001: Phạm vi chuẩn hoá repository — chỉ thêm hygiene, không tổ chức lại cấu trúc

**Ngày:** 2026-08-06
**Trạng thái:** Đã chấp nhận
**Người quyết định:** Bảo

## Bối cảnh

Một yêu cầu chuẩn hoá repository toàn diện (15 phase) được đưa ra, giả định:

1. Team gồm Bảo/Hưng/Hường/Hiển, với Hường sở hữu workstream "behavioral ML" (ABM, tabular/temporal)
   và Hiển sở hữu workstream "graph ML" (entity resolution, graph analytics) — hai workstream độc
   lập cần ranh giới import bị chặn bằng test kiến trúc.
2. Cấu trúc monorepo mục tiêu dạng `apps/ + services/ + ml/{behavioral,graph} + contracts/ +
   packages/ + infrastructure/ + deployment/` — phù hợp cho một hệ thống nhiều service độc lập.

Audit đầy đủ (`docs/repository/REPOSITORY_AUDIT.md`) phát hiện:

- Team thật, theo `WORKLOG.md`, là **Bảo/Hưng/Tin Tin/Hiển** — không có ai tên Hường.
- Không có hai workstream ML độc lập nào tồn tại trong code. Chỉ có một bộ sinh dữ liệu ABM
  (`scripts/abm_generate.py`, do Bảo viết) và một agent LangGraph còn ở dạng khung mẫu chưa hiện
  thực (`src/agents/`, do Hiển sở hữu theo kế hoạch, chưa bắt đầu).
- Repo thật là một backend monolith (một image dùng chung cho api/worker/seed/producer) + một SPA +
  một pipeline ingestion tách biệt qua Docker Compose profile — không phải nhiều service độc lập.
  Cấu trúc hiện tại (`src/`, `web/`, `flink/`, `db/`, `scripts/`) đã hợp lý và có tài liệu tốt.

## Quyết định

1. **Không tạo `ml/behavioral/` và `ml/graph/`** cho tới khi có workstream ML thật với chủ sở hữu
   thật. Tạo trước sẽ là "architectural theater" — đúng thứ mà chính yêu cầu gốc cấm.
2. **Không tổ chức lại `src/`, `web/`, `flink/` vào `apps/`/`services/`.** Cấu trúc hiện tại đã bám
   sát stack thật; ép vào layout lý thuyết cho một hệ thống multi-service sẽ tạo chi phí di chuyển
   lớn mà không giải quyết vấn đề thật nào.
3. **Phạm vi Phase 2 trở đi chỉ gồm hygiene cấp repo còn thiếu thật sự:** `.github/CODEOWNERS`,
   `.github/pull_request_template.md`, `CONTRIBUTING.md`, `SECURITY.md`, `LICENSE`,
   `.editorconfig`, `.gitattributes`, `docs/adr/`, `docs/repository/DEPENDENCY_REPORT.md`, và vá hai
   khoảng trống tài liệu đã xác minh (biến môi trường Flink chưa được liệt kê trong
   `.env.example`; comment lạc hậu trong `web/.env.example`).
4. CODEOWNERS dùng placeholder `TODO` cho username GitHub của Tin Tin và Hiển — chưa xác nhận được
   từ lịch sử commit (Hiển chưa có commit nào; tác giả `fiezen13` chỉ có một commit tài liệu, không
   đủ căn cứ để gán cho một người cụ thể).

## Hệ quả

- Nếu Hường thật sự tham gia team sau này (thay Tin Tin, hoặc thành viên thứ năm) và bắt đầu một
  workstream behavioral ML thật, tạo một ADR mới ghi nhận thời điểm đó và mở `ml/behavioral/` lúc
  đó — không hồi tố ADR này.
- Nếu quy mô hệ thống lớn lên tới mức cần tách nhiều service độc lập thật (không chỉ một image dùng
  chung), xét lại quyết định 2 bằng một ADR mới, dẫn chứng cụ thể service nào cần tách và vì sao.
- CODEOWNERS cần Bảo điền username GitHub thật của Tin Tin/Hiển trước khi coi là hoàn chỉnh.
