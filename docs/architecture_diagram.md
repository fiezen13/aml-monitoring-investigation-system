# Sơ đồ kiến trúc — FIN-07 AML Operations Console

Deliverable #3. Sơ đồ hệ thống và mô tả từng thành phần.

Tài liệu kiến trúc đầy đủ (sơ đồ triển khai, luồng request, bảo mật, CI/CD, sức
chứa): [`docs/architecture/architecture.md`](architecture/architecture.md).
Bản ảnh: [`docs/architecture/architecture.svg`](architecture/architecture.svg).

---

## 1. Sơ đồ tổng quan hệ thống

```mermaid
flowchart TB
    subgraph offline["Ngoại tuyến — scripts/ · KHÔNG chạy lúc phục vụ"]
        DATA["Dữ liệu công khai có nhãn<br/>IBM AML · SAML-D · Elliptic++"]
        RULE["Nhánh luật nghiệp vụ"]
        GRAPH["Nhánh đồ thị + MEGA-PNA<br/>FAN · GATHER_SCATTER · CYCLE"]
        BEH["Nhánh hành vi<br/>Isolation Forest 7 ngày"]
        FUSE["Hợp nhất điểm<br/>hiệu chuẩn chỉ fit trên train"]
        DATA --> RULE & GRAPH & BEH --> FUSE
    end

    subgraph serving["Đường phục vụ — VM GCP sau Caddy"]
        CADDY["Caddy 2.8<br/>TLS Let's Encrypt"]
        WEB["web · nginx<br/>SPA React + Vite"]
        API["api · FastAPI<br/>RBAC 3 vai · phiên PBKDF2"]
        WORKER["worker<br/>tác vụ bất đồng bộ"]
        REDIS[("Redis 7<br/>hàng đợi")]
        DB[("PostgreSQL 16<br/>điểm đã tính sẵn · cảnh báo<br/>vụ việc · nhật ký bất biến")]
    end

    AGENT["Tác tử điều tra<br/>Điều phối → Giải thích → Phản biện"]
    GEMINI["Google Gemini API"]
    HUMAN(["Chuyên viên · Quản lý · Quản trị"])

    FUSE -->|"nạp điểm + mã băm SHA-256"| DB
    HUMAN -->|HTTPS| CADDY --> WEB -->|"/api"| API
    API <--> DB
    API --> REDIS --> WORKER --> AGENT
    WORKER --> DB
    AGENT -.->|"7 công cụ CHỈ ĐỌC"| DB
    AGENT -.-> GEMINI
    AGENT ==>|"hồ sơ có dẫn chứng<br/>HOẶC chưa đủ bằng chứng"| HUMAN
```

**Ba ranh giới bắt buộc trong sơ đồ trên:**

1. **Mô hình không chạy lúc phục vụ.** API chỉ đọc điểm đã tính sẵn trong
   PostgreSQL. Không có `joblib.load` hay `torch.load` nào trong đường phục vụ.
2. **Tác tử luôn bất đồng bộ và luôn chỉ đọc** — cưỡng chế bằng vai trò
   PostgreSQL chỉ có `SELECT`, không phải bằng quy ước.
3. **Đường ra của tác tử luôn kết thúc ở con người.** Không có nhánh thứ ba.

---

## 2. Luồng điều tra một cảnh báo

```mermaid
flowchart TD
    H(["Chuyên viên bấm<br/><b>Điều tra bằng tác tử</b>"])
    SUP["<b>1 · Điều phối</b><br/>chọn công cụ cần gọi tiếp"]
    T[("<b>7 công cụ chỉ-đọc</b><br/>allow-list cứng<br/>không phát SQL, không tự tính số")]
    EXP["<b>2 · Giải thích</b><br/>mỗi khẳng định kèm mã bằng chứng"]
    CRI{"<b>3 · Phản biện</b><br/>đối chiếu TỪNG con số<br/>với bằng chứng viện dẫn"}
    OK["Hồ sơ có dẫn chứng<br/>chờ Quản lý ký"]
    NO["INSUFFICIENT_EVIDENCE<br/>kèm danh sách chỗ còn hổng"]

    H --> SUP --> T --> EXP --> CRI
    CRI -- "đạt" --> OK
    CRI -- "chưa đạt · còn ngân sách" --> SUP
    CRI -- "hết 5 vòng hoặc 16 lượt công cụ" --> NO
```

---

## 3. Quy trình vụ việc — hai vai, sáu trạng thái

```mermaid
stateDiagram-v2
    [*] --> TiepNhanCanhBao
    TiepNhanCanhBao --> SoanHoSoNghiVan: chuyên viên điều tra
    SoanHoSoNghiVan --> ChoNguoiPheDuyet: chuyên viên trình
    ChoNguoiPheDuyet --> XuatHoSo: quản lý duyệt
    ChoNguoiPheDuyet --> DongKhongBaoCao: quản lý chốt, không báo cáo
    ChoNguoiPheDuyet --> DieuTraBoSung: quản lý trả lại
    DieuTraBoSung --> SoanHoSoNghiVan
    XuatHoSo --> [*]
    DongKhongBaoCao --> [*]
```

Người **lập** và người **duyệt** khác **vai**, không chỉ khác người: Quản lý cố ý
không có quyền `prepare_sar`.

---

## 4. Mô tả thành phần

| Thành phần | Công nghệ | Vai trò |
|---|---|---|
| **Caddy** | Caddy 2.8-alpine | TLS tự động (Let's Encrypt), HTTP→HTTPS, security headers |
| **web** | nginx + React 18 + TypeScript + Vite | SPA console 3 vai trò; proxy `/api` và `/grafana` |
| **api** | FastAPI 0.141 · uvicorn · Python 3.11 | REST API, phân quyền mặc-định-đóng, phiên PBKDF2 200k vòng |
| **worker** | Python | Chạy phiên điều tra bất đồng bộ qua hàng đợi Redis |
| **PostgreSQL** | PostgreSQL 16 (Cloud SQL) | Giao dịch, cảnh báo, vụ việc, nhật ký kiểm toán bất biến, điểm mô hình đã tính sẵn |
| **Redis** | Redis 7-alpine | Hàng đợi tác vụ giữa api và worker |
| **Tác tử điều tra** | Google Gen AI SDK · Gemini | Ba vai sinh diễn giải có dẫn chứng; chỉ đọc, có trần chi phí |
| **Nhánh phát hiện** | scikit-learn · PyTorch Geometric · NetworkX · DuckDB | Chấm điểm ngoại tuyến, ghi vào CSDL kèm mã băm mô hình |
| **Nạp dữ liệu luồng** | Kafka · Flink (Java) · HDFS | Đã dựng và chạy end-to-end ở local-dev; **chưa triển khai production** |
| **Quan trắc** | OpenTelemetry · Prometheus · Loki · Jaeger · Grafana | Chỉ số, nhật ký, vết phân tán; nhúng trong console |

---

## 5. Tài liệu liên quan

| Tài liệu | Nội dung |
|---|---|
| [Kiến trúc đầy đủ](architecture/architecture.md) | Sơ đồ triển khai, luồng request, bảo mật, CI/CD, sức chứa |
| [Đặc tả hệ thống](specification/system-specification.md) | Phân tích nghiệp vụ, tuyên bố vấn đề, phạm vi |
| [Yêu cầu chức năng](specification/functional-requirements.md) | Vai trò, ma trận quyền, màn hình, quy trình |
| [Thiết kế kỹ thuật](specification/technical-design.md) | Thuật toán phát hiện, tầng tác tử, quyết định thiết kế |
| [Mô hình dữ liệu](specification/data-model.md) | Nguồn dữ liệu, lược đồ CSDL, đặc trưng, hợp đồng, lineage mô hình |
| [Kiểm thử](testing/test-plan.md) | Kế hoạch, ca kiểm thử và báo cáo |
