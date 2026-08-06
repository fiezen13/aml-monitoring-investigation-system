# Dependency Report — FIN-07

**Ngày quét:** 2026-08-06
**Công cụ:** `pip-audit 2.10.1` (đối chiếu môi trường Python cục bộ đã cài `requirements.txt` +
`requirements-dev.txt`), `npm audit` (`web/`, npm lockfile hiện có). Không chạy Trivy/Grype cho
Docker image trong lần quét này — xem mục "Đề xuất" bên dưới.

## 1. Lỗ hổng đã biết

### Python (`pip-audit`)

| Package | Version hiện tại | Advisory | Mức | Ghi chú |
|---|---|---|---|---|
| `cryptography` | 49.0.0 (transitive qua `google-auth` ← `langchain-google-genai`) | `PYSEC-2026-3552` / `CVE-2026-69247` — Bleichenbacher oracle trong `pkcs7_decrypt_*` | Trung bình theo CVSS, nhưng **không khai thác được trong FIN-07** — hệ thống không giải mã `EnvelopedData`/S-MIME từ nguồn không tin cậy ở đâu cả; `cryptography` chỉ được dùng gián tiếp cho việc ký/xác thực gọi Google API. | An toàn nâng cấp — không phải dependency trực tiếp, chỉ cần `google-auth`/`langchain-google-genai` kéo phiên bản mới hơn. Fix tại `cryptography>=50.0.0`. |

Không phát hiện lỗ hổng nào ở `fastapi`, `pydantic`, `sqlalchemy`, `psycopg`, `redis`,
`confluent-kafka`, `langchain*`, `langgraph`, `uvicorn`, hay bất kỳ dependency trực tiếp nào khác
trong `requirements.txt`.

*(`pip` chính nó — công cụ cài đặt trong virtualenv cục bộ, phiên bản 25.3 — có vài CVE đã biết,
nhưng đây không phải một dependency của ứng dụng, không được đóng gói vào Docker image
(`python:3.11-slim` build lại venv riêng), nên không đưa vào bảng trên.)*

### Frontend (`npm audit`, `web/`)

| Package | Range bị ảnh hưởng | Advisory | Mức | Fix |
|---|---|---|---|---|
| `react-router` (transitive), `react-router-dom` (trực tiếp, `^6.28.1`) | `>=6.0.0 <7.18.0` | `GHSA-wrjc-x8rr-h8h6` (open redirect via backslash), `GHSA-337j-9hxr-rhxg` (constructor injection qua `deserializeErrors` SSR), `GHSA-jjmj-jmhj-qwj2` (open redirect → XSS) | Trung bình (moderate) | `npm audit fix` giải quyết được trong phạm vi semver hiện tại (đã kiểm chứng bằng `npm audit fix --dry-run`, không cần `--force`/major bump thủ công) |

Không phát hiện lỗ hổng `high`/`critical` nào. Tổng 244 package được audit (66 prod, 178 dev).

## 2. Dependency không dùng tới

| Package | Khai báo ở | Trạng thái | Đề xuất |
|---|---|---|---|
| `chromadb` | `requirements.txt` (comment out) | Không cài, nhưng `CHROMA_PERSIST_DIR` vẫn có trong `src/config.py`/`.env.example` | Giữ nguyên comment-out cho tới khi tính năng vector store thật được xây; ghi rõ "planned, not active" trong `docs/ENVIRONMENT.md` để không ai tưởng đây là bug |
| `langchain-openai` | `requirements.txt` | Cài nhưng **không có lời gọi `ChatOpenAI` nào** trong `src/` — provider LLM thật đang dùng là Gemini qua `langchain-google-genai` (`src/services/llm.py`) | Giữ lại nếu dự định dùng OpenAI làm phương án dự phòng (đúng comment trong `.env.example`); nếu không có kế hoạch đó trong 1-2 sprint tới, có thể gỡ để giảm bề mặt tấn công/kích thước image |

Không phát hiện dependency trùng lặp (hai thư viện làm cùng một việc) ở cả Python lẫn npm.

## 3. Phiên bản không nhất quán

Không phát hiện. `requirements.txt`/`requirements-dev.txt` đều dùng ràng buộc `>=`, không pin cứng,
không có hai bản của cùng thư viện. `web/package.json` chỉ có một lock file (`package-lock.json`,
npm) — không lẫn `yarn.lock`/`pnpm-lock.yaml`.

## 4. Đề xuất nâng cấp

### An toàn ngay (safe now)

- `npm audit fix` trong `web/` — vá `react-router`/`react-router-dom`, nằm trong phạm vi semver
  `^6.28.1` đã khai báo, không phải breaking change theo npm.
- Để `cryptography` tự nâng theo transitive resolution lần cài tiếp theo (`pip install -r
  requirements.txt` với `google-auth` bản mới hơn) — không cần pin thủ công.

### Cần kiểm thử/migration (requires migration)

- Không có mục nào trong phạm vi quét lần này — không phát hiện nâng cấp major nào bị chặn bởi lỗ
  hổng.

### Hoãn lại (defer)

- Gỡ `langchain-openai` nếu xác nhận không cần fallback OpenAI — cần Bảo/Hiển xác nhận trước vì đây
  là quyết định về phương án dự phòng LLM provider, không phải vấn đề bảo mật.
- `chromadb` — kích hoạt khi có thiết kế vector store thật, không phải việc của lần chuẩn hoá này.

## 5. Chưa làm — nói rõ ra

- **Không có quét lỗ hổng image Docker (Trivy/Grype) trong CI.** `docs/CICD.md` mục 8 đã tự ghi
  nhận việc này còn thiếu trước khi bàn giao. Đề xuất thêm một job `security-scan` (path-filtered,
  chỉ chạy khi `Dockerfile`/`requirements.txt`/`web/package.json`/`docker/flink/Dockerfile` đổi) vào
  `.github/workflows/ci.yml`, không chặn merge ngay (do CI hiện đã sát mốc 8 phút) — nên chạy như
  job không bắt buộc trước, rồi thêm vào `needs` của job `ci` sau khi đã ổn định.
- **Không quét lỗ hổng phía Java/Maven (`flink/aml-ingestion/pom.xml`)** trong lần audit này — đề
  xuất chạy `mvn org.owasp:dependency-check-maven:check` như một job riêng nếu ingestion pipeline
  tiến gần production hơn.
</content>
