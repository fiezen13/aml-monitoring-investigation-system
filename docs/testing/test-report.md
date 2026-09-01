# Báo cáo kiểm thử — FIN-07

Kết quả kiểm thử thực tế của FIN-07 AML Operations Console. Mọi con số dưới đây
đến từ một lượt chạy có thật — kiểm thử tự động, gọi API bằng token thật, trình
duyệt headless điều khiển bản đã build, hoặc lượt gọi Gemini thật. Không có số
ước lượng.

Tài liệu liên quan: [kế hoạch kiểm thử](test-plan.md) ·
[danh mục ca kiểm thử](test-cases.md).

---

## 1. Tóm tắt

| Hạng mục | Kết quả |
|---|---|
| Kiểm thử tự động Python | **679 ca / 94 file** — xanh trên CI có PostgreSQL và Redis thật |
| Kiểm thử tự động giao diện | **15 file** Vitest — xanh; `tsc --noEmit` và `vite build` sạch |
| Hợp đồng dữ liệu | `make contracts-check` xanh — mọi schema chấp nhận ví dụ hợp lệ **và** từ chối ví dụ không hợp lệ |
| Dựng từ máy trống | Job `compose-smoke` xanh — `docker compose up` trên máy sạch, mọi dịch vụ `healthy` |
| Rà soát phân quyền thủ công | 5 vai × 22 route GET + 7 route ghi + 12 lần gõ thẳng URL |
| Đánh giá tác tử (Gate 2) | 5 ca với Gemini thật, phủ cả ba nhánh phát hiện |
| Rà soát chất lượng tác tử | 300 phiên + 80 phiên kiểm chứng lại |
| Lỗi tìm được trong đợt rà soát | **P0: 0 · P1: 1 · P2: 3 · P3: 1 · P4: 4** |
| Lỗi đã sửa và kiểm chứng lại | P1 và cả ba P2 |

**Kết luận:** không còn đường truy cập dữ liệu trái phép nào đang mở. Phần còn
lại là độ phủ trực quan, thiết kế đáp ứng, và nợ kỹ thuật hợp nhất ba bảng phân
quyền — không hạng mục nào chặn việc trình diễn.

---

## 2. Rà soát phân quyền và giao diện

**Ngày:** 20/08/2026 · **Môi trường:** stack đang chạy (không phải rà soát mã
tĩnh) · **Trình duyệt:** headless, khung nhìn 1440×900 · **CSDL:** PostgreSQL 16
(`fin07_hi_medium`) · **Tác tử:** Gemini `gemini-3.1-flash-lite`, khoá nằm trong
container worker.

> **Lưu ý về vai trò.** Đợt rà soát này chạy trên mô hình **năm vai trò** (`analyst`,
> `compliance_officer`, `mlro`, `auditor`, `admin`). Sau đó hệ thống gộp còn **ba
> vai** (migration [`029_role_consolidation.sql`](../../db/init/029_role_consolidation.sql)):
> `compliance_officer` + `mlro` + `auditor` → `manager`. Các phát hiện dưới đây
> vẫn còn giá trị vì chúng nói về **cơ chế** phân quyền, không về tên vai trò. Ma
> trận hiện hành nằm ở [yêu cầu chức năng §2](../specification/functional-requirements.md#2-ma-trận-quyền).

### 2.1 Phát hiện chính

- **Phân quyền phía máy chủ vững.** Chính sách mặc-định-đóng; mọi thao tác ghi
  đều có cổng đúng; vai chỉ-đọc bị chặn mọi thao tác ghi; chỉ đúng một vai qua
  được cổng phê duyệt; quản trị hệ thống bị từ chối suy luận mô hình. **Kiểm
  chứng bằng thực nghiệm, không đọc mã.**
- **Một lỗi kiểm soát truy cập thật (P1, IDOR).** Chi tiết vụ việc và đồ thị
  mạng lưới **bỏ qua** phạm vi dữ liệu mà danh sách vụ việc đã áp — chuyên viên
  đọc được vụ việc bất kỳ bằng cách đoán mã. **Đã sửa.**
- **Nguyên nhân gốc: ba bảng phân quyền song song đã trôi lệch nhau.** Hệ quả
  quan sát được: một vai trò có menu dẫn thẳng tới trang 403. **Đã đối chiếu và sửa.**
- **Tính có căn cứ của tác tử rất tốt.** Kết quả chạy trực tiếp: mọi khẳng định
  gắn bằng chứng, **không có dẫn chứng bịa**, ngôn ngữ AML dè dặt đúng mực, địa lý
  được trình bày như một **hành lang thống kê** chứ không phải một nhãn FATF.

### 2.2 Ma trận vai × route (kiểm chứng trực tiếp, sau khi sửa)

`200` = qua cổng phân quyền · `403` = bị từ chối.

| Route (GET) | analyst | compliance | mlro | auditor | admin |
|---|:--:|:--:|:--:|:--:|:--:|
| `/alerts`, `/alerts/page` | 200 | 200 | 200 | 200* | 403 |
| `/cases` | 200 | 200 | 200 | 200* | 403 |
| `/transactions` | 200 | 200 | 200 | 200 | 403 |
| `/fc/graph` | 200 | 200 | 200 | 200* | 403 |
| `/fc/crypto` | 200 | 200 | 200 | 403 | 403 |
| `/fc/agent-runs` | 200 | 200 | 200 | 200 | 403 |
| `/fc/benchmarks`, `/fc/data-quality`, `/fc/model-*` | 403 | 200 | 200 | 200 | 200 |
| `/sars` | 403 | 200 | 200 | 403 | 403 |
| `/audit` | 403 | 200 | 200 | 200 | 200 |
| `/users`, `/settings` | 403 | 403 | 403 | 403 | 200 |
| `/dashboard`, `/world`, `/queue`, `/status`, `/nav-counts` | 200 | 200 | 200 | 200 | 200 |

`*` = chỉ đọc; mọi thao tác ghi vẫn 403.

| Thao tác ghi (kiểm chiều âm) | analyst | compliance | mlro | auditor | admin |
|---|:--:|:--:|:--:|:--:|:--:|
| `POST /alerts/{id}/investigate` | qua cổng | qua cổng | qua cổng | **403** | 403 |
| `POST /cases/{id}/investigate` | qua cổng | qua cổng | qua cổng | **403** | 403 |
| `POST /approvals/{id}/decision` | 403 | 403 | **qua cổng** | 403 | 403 |
| `PATCH /users/{id}` | 403 | 403 | 403 | 403 | **qua cổng** |
| `PUT /settings/{code}` | 403 | 403 | 403 | 403 | **qua cổng** |
| `POST /aml/bitcoin/predict` | qua cổng | qua cổng | qua cổng | **403** | 403 |

Đây đúng là ma trận mong muốn: chỉ một vai quyết định phê duyệt, chỉ quản trị hệ
thống chạm người dùng/cấu hình, vai kiểm toán chỉ đọc ở mọi nơi, và quản trị hệ
thống **không** có thẩm quyền quyết định AML lẫn quyền chạy suy luận mô hình.

### 2.3 Danh sách lỗi

| Mã | Mức | Khu vực | Vấn đề | Trạng thái |
|---|---|---|---|---|
| AML-QA-002 | **P1** | `/cases/{id}`, `/cases/{id}/network` | IDOR cấp đối tượng: chi tiết và đồ thị bỏ qua phạm vi dữ liệu mà danh sách đã áp | **ĐÃ SỬA** |
| AML-QA-001 | **P2** | menu → cảnh báo/vụ việc/đồ thị | Ba bảng phân quyền trôi lệch; menu của vai kiểm toán dẫn tới trang 403 | **ĐÃ SỬA** |
| AML-QA-003 | **P2** | `/cases` | Không vụ việc nào có người được giao → không trình diễn được đường phạm vi dương | **ĐÃ SỬA** (script seed idempotent) |
| AML-QA-004 | **P2** | bảng điều khiển chuyên viên | Tổng cảnh báo toàn tổ chức bị gán nhãn "được giao cho tôi" — mô tả sai một phạm vi chưa được cưỡng chế | **ĐÃ SỬA** |
| AML-QA-009 | P3 | `config/nav.ts` | Mảng `NAV[].roles` trở thành thừa và một số mục lệch ma trận | Còn mở (đã ghi nhận) |
| AML-QA-005 | P4 | huy hiệu menu | Hiển thị số thô 5 chữ số, tràn khỏi chip | **ĐÃ SỬA** (`999+`) |
| AML-QA-006 | P4 | `/fc/agent-runs` | `step_count` = 0 trong khi dấu vết có 25 sự kiện | Còn mở (đã ghi nhận) |
| AML-QA-007 | P4 | trang `/403` | Đồng hồ giả bị đóng băng và mã yêu cầu tĩnh | Còn mở (đã ghi nhận) |
| AML-QA-008 | P4 | `/network` | Cảnh báo console vô hại của cytoscape | Còn mở (đã ghi nhận) |

Sửa xong chạy lại toàn bộ: kiểm thử API **75 đạt / 9 bỏ qua**, kiểm thử đơn vị
phân quyền **52 đạt**, `tsc --noEmit` sạch, `vite build` sạch.

### 2.4 Chất lượng giao diện và đồ thị

- Năm bảng điều khiển đều dựng từ **dữ liệu endpoint thật**, trạng thái rỗng nói
  thật ("chưa có dữ liệu" / "chưa có endpoint"), và **không có `Math.random`** bịa
  số. Console sạch trên mọi bảng.
- Đồ thị mạng lưới (162 nút / 238 cạnh): bố cục force-directed, 46 nút rủi ro cao
  tô đỏ tách bạch rõ khỏi khối rủi ro thấp, kích thước nút mã hoá độ lớn, đường
  dòng tiền trung tâm được làm nổi kèm mũi tên chỉ hướng. Nhận ra cụm đáng ngờ
  trong vài giây. Điểm yếu: nhãn chồng nhau ở vùng lõi dày khi để mức phóng mặc định.
- Bảng tóm tắt cấu trúc: 12 đường đi, 8 chu trình, 46 nút rủi ro cao, độ phủ bằng
  chứng 100%, tổng dòng tiền đa tiền tệ, và thuật lại bằng ngôn ngữ tự nhiên có
  trích mã tài khoản và số tiền thật. Số 0 được hiển thị trung thực.

### 2.5 Hiệu năng quan sát được

| Phép đo | Kết quả |
|---|---|
| Một phiên điều tra đầu–cuối (3 lượt gọi LLM tuần tự) | ≈ 9,4 giây, **bất đồng bộ** — trả `QUEUED` ngay, giao diện không bị chặn |
| Bundle giao diện | `index` ≈ 1,03 MB · `WorldPage` ≈ 1,10 MB (gzip ≈ 300 KB mỗi bundle). Vite cảnh báo >500 KB — chia mã là việc tối ưu về sau |
| Đồ thị 162 nút | Không đơ. Đồ thị lớn hơn **chưa** kiểm thử tải |

---

## 3. Đánh giá tác tử điều tra (Gate 2)

**Ngày:** 16/08/2026. Năm ca chạy thủ công trên bản đang phục vụ. **Không ca nào
chạy ở chế độ mô phỏng** — toàn bộ chín lượt tác tử trong mỗi ca đều gọi Gemini
thật (`model_provider = google-genai`, `gemini-3.1-flash-lite`); số token là số
nhà cung cấp trả về.

| # | Cảnh báo | Nhánh | Điểm | Nhóm | Vòng | Công cụ | Token | Facts | Claims | Phản biện | Kết quả |
|---|---|---|---:|---|---:|---:|---:|---:|---:|---|---|
| 1 | `ALT-TRI-ea7a3d6acc951865` | đồ thị | 99,76 | T02 | 3 | 8 | 152.658 | 7 | 8 | FAIL · 5 vấn đề | Chưa đủ bằng chứng |
| 2 | `ALT-IF-a91a8104f979eaf7` | ML | 100,00 | T05 | 3 | 8 | 210.479 | 12 | 13 | FAIL · 2 vấn đề | Chưa đủ bằng chứng |
| 3 | `ALT-IF-2f9a70d0e19b21f2` | ML | 100,00 | T05 | 3 | 8 | 170.681 | 15 | 16 | FAIL · 3 vấn đề | Chưa đủ bằng chứng |
| 4 | `ALT-RULE-5b49940796f50640` | luật | 100,00 | T01 | 3 | 6 | 109.407 | 7 | 8 | FAIL · 2 vấn đề | Chưa đủ bằng chứng |
| 5 | `ALT-RULE-c9f5feded21a9038` | luật | 100,00 | T01 | 3 | 6 | 98.344 | 9 | 10 | FAIL · 4 vấn đề | Chưa đủ bằng chứng |

Năm ca phủ cả ba nhánh phát hiện và bốn nhóm hành vi khác nhau.

> **Cột "Vòng" và "Công cụ" là số đo tại thời điểm chạy.** Khi đó trần là 3 vòng
> / 8 lượt gọi công cụ. Trần hiện tại đã nâng lên **5 vòng / 16 lượt** — chính vì
> kết quả đợt đo này: thêm vòng mà giữ nguyên trần công cụ thì vòng thêm không có
> bằng chứng mới để đọc, chỉ viết lại trên đúng dữ liệu cũ.

### 3.1 Vì sao cả năm ca đều dừng ở "chưa đủ bằng chứng"

Đây là kết quả cần giải thích thẳng, không giấu sau một con số đẹp.

Tác tử phản biện là **phép kiểm tất định**, không phải một lời nhắc gửi cho mô
hình. Nó đối chiếu **từng con số** trong bản luận giải với gói bằng chứng được
viện dẫn. Con số nào không tìm thấy thì bị đánh dấu, và **một** khẳng định bị
đánh dấu là đủ để cả bản luận giải không qua.

**Trong cả năm ca, lý do phản biện đưa ra đều đúng:**

| # | Loại vấn đề | Nội dung thật mà phản biện bắt được |
|---|---|---|
| 1 | `MISSING_EVIDENCE` | Có điểm từ nhánh đồ thị nhưng chưa có bằng chứng có cấu trúc về mẫu hình tương ứng |
| 2 | `CONTRADICTION` | Sáu khẳng định trích dẫn nguồn chứng cứ không khớp nội dung |
| 3 | `UNSUPPORTED_CLAIM` | Giá trị `779944.0` không xuất hiện trong bằng chứng được viện dẫn |
| 4 | `CONTRADICTION` | Mốc thời gian trong luận giải lệch so với giao dịch thật |
| 5 | `MISSING_SOURCE_RECORD` | Mã bằng chứng được viện dẫn không tồn tại trong ngữ cảnh |

Nói cách khác: mô hình **có** bịa số và bịa dẫn chứng, và hàng rào **có** bắt
được. Đó là hành vi đúng thiết kế cho một hệ AML — một hồ sơ nghi vấn sai gửi đi
còn tốn kém hơn một hồ sơ không gửi. Hệ thống chuyển ca lại cho chuyên viên kèm
danh sách chỗ còn hổng, thay vì kết luận bừa.

**Đây cũng là giới hạn thật của bản MVP, cần nói rõ: chưa ca nào đi trọn đường
tới bản luận giải được duyệt tự động.** Muốn cải thiện thì phải giảm ảo giác ở
tác tử giải thích — **không phải** nới hàng rào phản biện.

### 3.2 Điểm yếu quan sát được ở tác tử điều phối

Ở ca 1, ba lượt `GetGraphEvidence` đều trả về thiếu một phần (tài khoản này không
có bản ghi trong `graph_detector_evidence`). Tác tử điều phối gọi lại **ba lần**
mà không rút ra rằng công cụ ấy sẽ không trả thêm gì. Phiên dừng vì hết trần tám
lượt gọi công cụ. Đã ghi nhận và xử lý một phần ở đợt rà soát mục 4 (lỗi #10).

---

## 4. Rà soát chất lượng tác tử (300 phiên)

**Ngày:** 19/08/2026 · **Công cụ:** [`scripts/audit_agent_runs.py`](../../scripts/audit_agent_runs.py).

Lấy mẫu cảnh báo theo từng cặp (bộ phát hiện, nhóm hành vi), chạy đúng quy trình
thật, rồi chấm mỗi phiên bằng **những phép kiểm tất định** — không hỏi mô hình
xem nó tự thấy mình viết tốt chưa.

| Đợt đo | Số phiên | Chạy xong | Phiên không lỗi |
|---|---:|---:|---:|
| Trước khi sửa | 12 | 75% | 50% |
| Sau đợt sửa 1 | 300 | 87% | 100% |
| Bản cuối | 300 | 99% | 94% |
| Kiểm chứng sau đợt sửa cuối | 80 | 99% | **100%** |

Riêng nhánh địa lý: **0/75 → 75/75** phiên chạy xong.

Ba lỗi `HARNESS_ERROR` ở đợt 300 là tranh chấp khoá do công cụ đo chạy 8 luồng
trên cùng một phiên, **không phải** đường chạy thật — cả ba đều chạy xong khi gọi
tuần tự như worker vẫn gọi.

### 4.1 Mười hai lỗi tìm ra và đã sửa

| # | Lỗi | Ảnh hưởng trước khi sửa |
|---|---|---|
| 1 | `REQUIRED_EVIDENCE` khoá theo hai giá trị không tồn tại trong bảng `alert` | Khối bổ sung bằng chứng đồ thị **chưa bao giờ chạy** |
| 2 | Hai tín hiệu địa lý không nhánh nào sinh ra | **5.004/5.004** cảnh báo địa lý trượt phản biện |
| 3 | Cửa sổ đặc trưng rỗng bị viết thành "không có giao dịch nào" | Câu tóm tắt phủ nhận đúng những giao dịch liệt kê ngay bên dưới |
| 4 | Bước bổ sung không kiểm cửa sổ rộng bao nhiêu | Tóm tắt 7 ngày đứng cạnh sổ giao dịch cả tháng → `CONTRADICTION` |
| 5 | Hàm che định danh xoá cả token toàn chữ số | `5016.80` bị cắt thành ` 16.80` → `UNSUPPORTED_CLAIM`. **Nguyên nhân trượt nhiều nhất** |
| 6 | Chỉ mục bằng chứng không kèm mã giao dịch | Phản biện kết luận "giao dịch không có trong danh mục" rồi đánh trượt |
| 7 | Bảng tên nhánh thiếu hai nhánh | Sinh ra câu vô nghĩa trên cả 10.004 cảnh báo |
| 8 | Chọn giao dịch dẫn chứng theo số tiền lớn nhất | Cảnh báo hành lang UK→UAE dẫn chứng bằng ba giao dịch **nội địa UK** |
| 9 | Duyệt mọi bằng chứng trùng nhau | Cùng một giao dịch được kể hai, ba lần |
| 10 | `GetGraphEvidence` không ghi lại kết quả âm tính | Không phân biệt "đã tra, không có" với "chưa ai tra" |
| 11 | Câu "chưa kiểm tra được X vì thiếu bằng chứng" không cho biết phải làm gì | Nay nêu lý do cụ thể, hoặc nói rõ đã tra và không thấy |
| 12 | Dấu phân cách số kiểu Anh trong văn bản tiếng Việt | `9,258` bị đọc thành 9,258 — cả người lẫn bộ đối chiếu số đều đọc sai |

### 4.2 Còn tồn tại

- **Hai mẫu số cho cùng một hành lang.** Điểm rủi ro tính theo mức nền của toàn
  bộ giao dịch (0,10%), trong khi nhánh địa lý chỉ xét giao dịch xuyên biên giới
  (mức nền 0,31%). Bản giải thích nay nêu **cả hai** kèm tên gọi rõ ràng, nhưng
  công thức chấm điểm chưa đổi — đổi nó là đổi thứ hạng của cả 5.004 cảnh báo.
- `GetTransactions` vẫn lấy 50 dòng gần nhất. Với tài khoản dày giao dịch, một
  hành lang có thật vẫn có thể nằm ngoài trang đầu.

---

## 5. Kết quả mô hình

Trích dẫn theo quy ước ở [`reports/README.md`](../../reports/README.md): chỉ khoá
`headline` của báo cáo mang `"schema_version": "fin07.benchmark.v1"`.

| Nhánh | Mô hình | Vùng dữ liệu | Kết quả |
|---|---|---|---|
| IBM AML (phục vụ hàng đợi chính) | MEGA-PNA chấm cạnh | IBM HI-Medium, 6.754.950 giao dịch | F1 0,7801 · PR-AUC 0,4949 · P 0,8399 · R 0,7282 |
| Bitcoin | Random Forest trên Elliptic | 67.504 giao dịch | F1 0,81 · PR-AUC 0,79 |
| SAML-D | Multi-PNA + Edge Updates | ≈ 1,4 triệu giao dịch vùng | F1 0,98 · PR-AUC 0,99 |

Dòng IBM đo trực tiếp trên release đang `active` ngày 01/09/2026
(`REL-MP-6707e0cfbc33679f`, `fin07_mega_pna_edge_v1`, ngưỡng `0,56933`,
11.016 nhãn dương trên 6.754.950 dòng = **0,163%**).

> **Release này chạy MỘT seed, không phải năm.** `best_epoch` 18 trên 28 epoch.
> Không có ước lượng dao động giữa các lần chạy, nên **không được viết kết quả
> dưới dạng trung bình ± độ lệch** — chính artifact release ghi rõ điều đó.

**Ba nhánh chấm trên ba vùng dữ liệu tách biệt và KHÔNG cộng gộp chỉ số** — khác
vùng, khác loại mô hình, khác bộ đo. So sánh trực tiếp ba cột kết quả này với
nhau là so sánh sai.

Báo cáo benchmark đầy đủ dạng nghiên cứu (15 bảng, 5 seed, khoảng tin cậy):
[`reports/edge-benchmark/hi_medium_currency_native_policy_v1.md`](../../reports/edge-benchmark/hi_medium_currency_native_policy_v1.md).

Nhắc lại từ [thiết kế kỹ thuật §2.6](../specification/technical-design.md#26-vì-sao-không-dùng-accuracy):
nhãn dương chiếm dưới 0,2% ở mọi bộ dữ liệu đang dùng (0,068% trên LI-Small,
0,163% trên HI-Medium), nên **accuracy không được dùng** ở bất kỳ đâu trong dự án.

---

## 6. Đánh giá mức độ sẵn sàng

| Khía cạnh | Điểm | Vì sao chưa đạt tối đa |
|---|:--:|---|
| Đúng chức năng | 8/10 | Luồng chính chạy; SAR đầu–cuối và xuất báo cáo chưa bấm kiểm hết trên trình duyệt |
| Phân quyền / bảo mật | 8/10 | Máy chủ vững; IDOR và trôi lệch tầng đã sửa. Trừ 2: "nguồn sự thật duy nhất" thực chất là ba bảng đồng bộ tay, và cảnh báo chưa có phạm vi cấp bản ghi |
| Quy trình AML | 8/10 | Cảnh báo → vụ việc → đồ thị → giải thích → leo thang mạch lạc. Trừ 2: dữ liệu phân công còn là seed demo, chưa phải đường vận hành |
| Nhất quán giao diện | 8/10 | Hệ thống thiết kế áp dụng nhất quán. Trừ 2 cho các vấn đề nhãn/huy hiệu (đã sửa) và siêu dữ liệu menu thừa |
| Chất lượng bảng điều khiển | 9/10 | Các bảng phân biệt rõ theo vai, dữ liệu thật, trạng thái rỗng trung thực |
| Chất lượng biểu đồ | 7/10 | Biểu đồ đã kiểm thì trung thực. Trừ 3 vì chưa đối chiếu từng biểu đồ với payload của nó |
| Khả dụng của đồ thị | 8/10 | Phân cấp, hướng và bằng chứng tốt. Trừ 2 cho nhãn chồng ở lõi và tương tác chưa quét hết |
| Độ chính xác tác tử | 9/10 | Chạy thật, phân rã điểm rủi ro đúng, khung diễn đạt AML đúng |
| Tính có căn cứ của tác tử | 9/10 | Gắn bằng chứng, không dẫn chứng bịa. Trừ 1 vì kiểm trên mẫu, không vét cạn |
| Thiết kế đáp ứng | 6/10 | Chỉ kiểm ở 1440×900; các mức nhỏ hơn chưa quét |
| Khả năng kiểm toán | 8/10 | `audit_log` bất biến, sự kiện vụ việc/SAR/đăng nhập được ghi. Trừ 2 vì sự kiện đổi vai / xuất báo cáo / cấu hình chưa ghi |

---

## 7. Giới hạn của đợt kiểm thử — nói thẳng

Những hạng mục **chưa** làm, ghi ra thay vì để trống:

- **Chưa vét cạn:** sắp xếp/lọc/phân trang của mọi bảng, mọi hộp thoại, và khả
  năng dùng hoàn toàn bằng bàn phím.
- **Thiết kế đáp ứng:** chỉ kiểm ở 1440×900. Các mức 1366×768, 1280×800 và bề
  ngang máy tính bảng chưa quét.
- **Biểu đồ:** chưa đối chiếu từng biểu đồ với payload API của nó.
- **Quy trình SAR:** kiểm ở mức cổng API và phân quyền, chưa bấm hết đầu–cuối
  trên trình duyệt.
- **Bộ dữ liệu:** nhánh IBM được kiểm sâu; SAML-D và Elliptic++ chưa rà soát sâu
  riêng trong đợt này.
- **Kiểm thử tải:** chưa làm. Đồ thị lớn hơn 162 nút chưa kiểm.
- **Kiểm thử xâm nhập của bên thứ ba:** chưa làm.
- **Đo trải nghiệm người dùng có người thật:** chưa làm, nên chỉ tiêu "giảm 40%
  thời gian xử lý một cảnh báo" trong [đặc tả hệ thống §9.2](../specification/system-specification.md#92-đối-chiếu-tiêu-chí-nghiệm-thu)
  chưa có số.

---

## 8. Việc cần làm tiếp

**Trước khi đưa vào vận hành thật**

1. Dẫn xuất `ROUTE_ROLES` và `NAV_PERMISSION` từ `permissions.py` — loại bỏ hẳn
   lớp lỗi "ba bảng trôi lệch".
2. Thêm cột người-được-giao cho `alert` và cưỡng chế phạm vi dữ liệu cấp bản ghi,
   **hoặc** giữ mô hình hàng đợi dùng chung một cách tường minh.
3. Mở rộng `audit_log` cho sự kiện đăng nhập, đổi vai trò, kích hoạt tài khoản,
   xuất báo cáo và đổi cấu hình.
4. Giảm ảo giác ở tác tử giải thích để có ca đi trọn đường tới bản luận giải đạt
   — **không** nới hàng rào phản biện.

**Nên có**

- Nhãn tránh chồng ở vùng lõi đồ thị; chia mã cho hai bundle lớn; quét đáp ứng
  đầy đủ ở 1366×768; phủ kiểm thử đầu–cuối cho SAR và xuất báo cáo.
