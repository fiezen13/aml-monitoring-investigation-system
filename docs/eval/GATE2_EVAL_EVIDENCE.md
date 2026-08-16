# Bằng chứng đánh giá — Gate 2

Năm ca chạy thủ công trên bản đang phục vụ tại <https://www.amlmonitoring.site>,
ngày 16/08/2026. Không có ca nào chạy ở chế độ mô phỏng: toàn bộ chín lượt tác
tử trong mỗi ca đều gọi Gemini thật (`model_provider = google-genai`,
`gemini-3.1-flash-lite`), và số token dưới đây là số nhà cung cấp trả về.

Cách tái lập từng ca nằm ở mục [Tái lập](#tái-lập) cuối tài liệu.

## Hệ thống đang đo cái gì

Một *user flow* hoàn chỉnh: chuyên viên mở một cảnh báo rủi ro cao và bấm
**Điều tra bằng tác tử**. Ba tác tử chạy nối tiếp, tối đa ba vòng:

1. **Điều phối** chọn công cụ nào cần gọi tiếp, dựa trên bằng chứng đã có.
2. **Giải thích** dựng bản luận giải, mỗi khẳng định phải kèm `evidence_refs`.
3. **Phản biện** soát lại bản luận giải và chỉ ra chỗ không đứng vững.

Đầu ra là một hồ sơ có dấu vết: từng lượt gọi công cụ, từng gói bằng chứng,
từng khẳng định và từng phản bác.

## Bảng tổng hợp

| # | Cảnh báo | Nhánh | Điểm | Nhóm | Vòng | Công cụ | Token | Facts | Claims | Phản biện | Kết quả |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `ALT-TRI-ea7a3d6acc951865` | graph | 99,76 | T02 | 3 | 8 | 152.658 | 7 | 8 | FAIL · 5 vấn đề | Chưa đủ bằng chứng |
| 2 | `ALT-IF-a91a8104f979eaf7` | ml | 100,00 | T05 | 3 | 8 | 210.479 | 12 | 13 | FAIL · 2 vấn đề | Chưa đủ bằng chứng |
| 3 | `ALT-IF-2f9a70d0e19b21f2` | ml | 100,00 | T05 | 3 | 8 | 170.681 | 15 | 16 | FAIL · 3 vấn đề | Chưa đủ bằng chứng |
| 4 | `ALT-RULE-5b49940796f50640` | rule | 100,00 | T01 | 3 | 6 | 109.407 | 7 | 8 | FAIL · 2 vấn đề | Chưa đủ bằng chứng |
| 5 | `ALT-RULE-c9f5feded21a9038` | rule | 100,00 | T01 | 3 | 6 | 98.344 | 9 | 10 | FAIL · 4 vấn đề | Chưa đủ bằng chứng |

Năm ca phủ cả ba nhánh phát hiện — luật nghiệp vụ, đồ thị, mô hình bất thường —
và bốn nhóm hành vi khác nhau.

## Vì sao cả năm ca đều dừng ở "chưa đủ bằng chứng"

Đây là kết quả cần giải thích thẳng, không nên giấu sau một con số đẹp.

Tác tử phản biện là **kiểm tra tất định**, không phải một lời nhắc gửi cho mô
hình. Nó đối chiếu từng con số trong bản luận giải với gói bằng chứng được viện
dẫn. Con số nào không tìm thấy trong bằng chứng thì bị đánh dấu, và một khẳng
định bị đánh dấu là đủ để cả bản luận giải không qua.

Với năm ca này, tất cả đều bị chặn — và **trong cả năm ca, lý do phản biện đưa
ra đều đúng**:

| # | Loại vấn đề | Nội dung thật mà phản biện bắt được |
|---|---|---|
| 1 | `MISSING_EVIDENCE` | Có điểm từ nhánh đồ thị nhưng chưa có bằng chứng có cấu trúc về mẫu hình/cạnh tương ứng |
| 2 | `CONTRADICTION` | Sáu khẳng định trích dẫn nguồn chứng cứ không khớp nội dung |
| 3 | `UNSUPPORTED_CLAIM` | Giá trị `779944.0` không xuất hiện trong bằng chứng được viện dẫn |
| 4 | `CONTRADICTION` | Mốc thời gian trong luận giải lệch so với giao dịch thật (giao dịch 4687949) |
| 5 | `MISSING_SOURCE_RECORD` | Bằng chứng `EV-abeecde42e8d0b91b519c2d4` không tồn tại trong ngữ cảnh |

Nói cách khác: mô hình **có** bịa số và bịa dẫn chứng, và hàng rào **có** bắt
được. Đó là hành vi đúng thiết kế cho một hệ thống AML — một hồ sơ nghi vấn sai
gửi đi còn tốn kém hơn một hồ sơ không gửi. Hệ thống chuyển ca cho chuyên viên
kèm danh sách chỗ còn hổng, thay vì kết luận bừa.

Điều này cũng là giới hạn thật của bản MVP, cần nói rõ: **chưa ca nào đi trọn
đường tới bản luận giải được duyệt tự động.** Muốn cải thiện thì phải giảm ảo
giác ở tác tử giải thích, không phải nới hàng rào phản biện.

## Chi tiết từng ca

### Ca 1 — `ALT-TRI-ea7a3d6acc951865` · nhánh đồ thị · T02

Tài khoản `20:8002229A0`, điểm rủi ro 99,76.

Bản luận giải:

> Trong cửa sổ từ 2022-08-13 đến 2022-09-12, tài khoản nhận 46.503,28 USD từ 3
> đối tác và chuyển đi 8.486.233.181,59 USD tới 11 đối tác.

Công cụ đã gọi: `GetRiskBreakdown`, `GetGraphEvidence` (thiếu một phần),
`GetGraphNeighborhood`, `GetTransactions`, `GetTypology`, `GetGraphEvidence`,
`GetAccountBehavior`, `GetGraphEvidence`.

Ba lượt `GetGraphEvidence` đều trả về **thiếu một phần** — tài khoản này không
có bản ghi trong `graph_detector_evidence`. Tác tử điều phối gọi lại ba lần, và
đó là điểm yếu đáng ghi nhận: nó không rút ra rằng công cụ ấy sẽ không bao giờ
trả thêm gì. Phiên dừng vì hết trần tám lượt gọi công cụ.

### Ca 2 — `ALT-IF-a91a8104f979eaf7` · nhánh mô hình bất thường · T05

Tài khoản `70:10042B738`, điểm 100,00. 210.479 token — ca tốn nhất trong năm ca.

> Trong cửa sổ từ 2022-09-03 đến 2022-09-10, tài khoản nhận 20.760,74 USD từ 65
> đối tác và chuyển đi 1.128.665.069,34 USD tới 1.196 đối tác.

Chênh lệch vào–ra hơn năm bậc độ lớn với 1.196 đối tác nhận là dấu hiệu trung
chuyển rõ. Phản biện bắt được sáu khẳng định trích dẫn nguồn không khớp.

### Ca 3 — `ALT-IF-2f9a70d0e19b21f2` · nhánh mô hình bất thường · T05

Tài khoản `70:10042B660` — **222.037 giao dịch gửi, 1.553 nhận**. Đây là ca nặng
nhất trong dữ liệu và cũng là ca từng làm lộ bốn lỗi hiệu năng nghiêm trọng
(xem `docs/BAO_CAO_HOAN_THIEN_HE_THONG.md`). Trước khi sửa, phiên điều tra chạy
**44 phút và không bao giờ kết thúc**; sau khi sửa còn **83 giây**.

> Trong cửa sổ từ 2022-09-03 đến 2022-09-10, tài khoản nhận 336.305,52 USD từ
> 767 đối tác và chuyển đi 27.342.542.139,81 USD tới 14.498 đối tác.

Phản biện bắt: giá trị `779944.0` không xuất hiện trong bằng chứng được viện dẫn.

### Ca 4 — `ALT-RULE-5b49940796f50640` · nhánh luật nghiệp vụ · T01

Tài khoản `0:8001263A0`, điểm 100,00, yếu tố đóng góp chính `R04_CROSS_BORDER_FLOW`
(96,19) và `R01_STRUCTURING` (55,56).

Ca này cho thấy một hạn chế thật của dữ liệu: cửa sổ quan sát tính đến mốc ảnh
chụp **không có giao dịch nào**, nên tác tử không mô tả được hành vi cụ thể mà
chỉ thuật lại điểm số. Phản biện đánh dấu chính điều đó là khẳng định thiếu căn
cứ. Hệ thống nói ra chỗ nó không biết thay vì lấp đầy bằng suy đoán.

Câu hỏi mở mà tác tử điều phối tự đặt ra:

> Tại sao các giao dịch lại được thực hiện theo chuỗi số tiền lặp lại
> (72.933,49 · 41.015,43 · 8.678,97) một cách có hệ thống?

### Ca 5 — `ALT-RULE-c9f5feded21a9038` · nhánh luật nghiệp vụ · T01

Tài khoản `0:8008B0600`, điểm 100,00.

> Trong cửa sổ từ 2022-09-03 đến 2022-09-10, tài khoản nhận 1.082.999,68 USD từ
> 2 đối tác và chuyển đi 248.588,86 USD tới 6 đối tác.

Phản biện bắt lỗi nặng nhất trong năm ca: bằng chứng `EV-abeecde42e8d0b91b519c2d4`
được viện dẫn **không tồn tại**. Mô hình bịa ra một mã bằng chứng, và hàng rào
bắt được vì nó đối chiếu với sổ bằng chứng thật chứ không tin lời mô hình.

## Kết luận rút ra

**Chạy được đầu–cuối với LLM thật.** Năm ca, ba nhánh phát hiện, 741.569 token
qua Gemini, không ca nào dùng mô phỏng.

**Hàng rào chống ảo giác hoạt động.** Năm trên năm ca bắt được lỗi thật: bịa số,
bịa mã bằng chứng, sai mốc thời gian, trích dẫn không khớp. Không có ca nào bị
chặn oan.

**Chi phí đo được, có trần.** Trung bình ~148.000 token và 25–32 giây thời gian
tác tử cho mỗi phiên. Trần ba vòng và tám lượt gọi công cụ đảm bảo một phiên
không bao giờ chạy vô hạn — cả năm ca đều dừng vì chạm trần chứ không vì lỗi.

**Điểm yếu đã thấy.** Ca 1 gọi lại `GetGraphEvidence` ba lần trong khi công cụ
đó chắc chắn không trả thêm gì. Tác tử điều phối cần nhớ công cụ nào đã cạn.

## Tái lập

```bash
BASE=https://www.amlmonitoring.site
TOKEN=$(curl -s -X POST "$BASE/api/v1/auth/login" \
  -H 'Content-Type: application/json' \
  -d '{"email":"tuan.la@velrix.vn","password":"demo-password"}' | jq -r .token)

ALERT=ALT-RULE-5b49940796f50640   # đổi thành mã bất kỳ trong bảng trên

curl -s -X POST -H "Authorization: Bearer $TOKEN" \
  "$BASE/api/v1/alerts/$ALERT/investigate" | jq

# Chờ 40–90 giây rồi đọc kết quả
INV=$(curl -s -H "Authorization: Bearer $TOKEN" \
  "$BASE/api/v1/alerts/$ALERT/investigation" | jq -r .investigation_id)
curl -s -H "Authorization: Bearer $TOKEN" "$BASE/api/v1/investigations/$INV/explanation" | jq
curl -s -H "Authorization: Bearer $TOKEN" "$BASE/api/v1/investigations/$INV/trace"       | jq
```

Mỗi lần chạy lại tạo một phiên mới, nên câu chữ của mô hình sẽ khác. Phần không
đổi là cấu trúc: facts kèm `evidence_refs`, phản biện tất định, và trần chi phí.
