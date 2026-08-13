### **DỰ ÁN FIN-07**

# **AI AGENT PHÁT HIỆN RỬA TIỀN (AML) VÀ GIÁM SÁT TUÂN THỦ**

**TÀI LIỆU PHÂN TÍCH NGHIỆP VỤ & TUYÊN BỐ VẤN ĐỀ**

|**Hạng mục**|**Nội dung**|
|---|---|
|Mã dự án|FIN-07|
|Loại tài liệu|Business Analysis Document (BAD) — Domain & Problem Statement|
|Phiên bản|v1.0|
|Ngày phát hành|27/07/2026|
|Chu kỳ thực hiện|5 tuần — từ 28/07/2026 đến 31/08/2026|
|Người lập / chủ sở hữu|Bảo — Project Manager kiêm DevOps|
|Nhóm thực hiện|Bảo (PM/DevOps), Hưng (Frontend), Tin Tin (Backend), Hiển (AI<br>Engineer)|
|Đối tượng đọc|Nhóm dự án, MLRO/Compliance, Ban lãnh đạo, đơn vị kiểm toán nội bộ|
|Mức độ mật|Nội bộ — Hạn chế (tài liệu chứa mô tả phương pháp giám sát)|



FIN-07 — Tài liệu phân tích nghiệp vụ AML | Nội bộ | Trang 1

## **MỤC LỤC**

_(Nếu mục lục chưa hiển thị: mở file bằng Word, nhấn Ctrl+A rồi F9 để cập nhật.)_

FIN-07 — Tài liệu phân tích nghiệp vụ AML | Nội bộ | Trang 2

## **1. MỤC ĐÍCH, PHẠM VI VÀ CÁCH DÙNG TÀI LIỆU**

#### **1.1. Mục đích**

Tài liệu này trả lời ba câu hỏi trước khi nhóm viết dòng code đầu tiên: (i) rửa tiền thực chất diễn ra như thế nào và để lại dấu vết gì trên dữ liệu giao dịch; (ii) hiện nay khung pháp lý và các lực lượng chức năng tại Việt Nam đang phòng, chống rửa tiền bằng cách nào, quy trình ra sao; (iii) nỗi đau cụ thể mà bộ phận tuân thủ của một fintech và cả cơ quan quản lý đang chịu là gì, đau ở chỗ nào, đau bao nhiêu. Từ đó tài liệu đưa ra tuyên bố vấn đề (problem statement) làm cơ sở cho phạm vi sản phẩm và tiêu chí nghiệm thu của FIN-07.

Tài liệu KHÔNG phải là tài liệu thiết kế kỹ thuật (SDD) và cũng không phải tư vấn pháp lý. Mọi trích dẫn văn bản quy phạm pháp luật trong tài liệu là để định hướng nghiệp vụ; trước khi triển khai thật, các quy trình phải được bộ phận Pháp chế và MLRO của tổ chức rà soát và phê duyệt.

#### **1.2. Phạm vi**

- Trong phạm vi: giám sát giao dịch (transaction monitoring), phân tích mạng lưới giao dịch, điều tra tự động có bằng chứng, soạn thảo hồ sơ nghi vấn (STR/SAR), đối chiếu danh sách trừng phạt và PEP, quy trình phê duyệt có con người (HITL) và nhật ký kiểm toán.

- Ngoài phạm vi: eKYC/onboarding khách hàng, chấm điểm tín dụng, phòng chống gian lận thanh toán thời gian thực (fraud/authorisation), kết nối trực tiếp tới hệ thống báo cáo của cơ quan nhà nước, và mọi hành động tự động phong tỏa tài khoản không có người phê duyệt.

#### **1.3. Cách dùng**

Chương 2–3 là nền tảng nghiệp vụ dùng chung cho cả nhóm; Chương 4 là căn cứ để ưu tiên backlog; Chương 5–7 chuyển vấn đề thành phạm vi và tiêu chí đo lường. Mỗi hạng mục nỗi đau ở Chương 4 được đánh mã (P01…P14) và được tham chiếu ngược trong kế hoạch Jira kèm theo, để mọi user story đều truy vết được về một nỗi đau có thật.

FIN-07 — Tài liệu phân tích nghiệp vụ AML | Nội bộ | Trang 3

## **2. TỔNG QUAN NGHIỆP VỤ VỀ RỬA TIỀN**

#### **2.1. Bản chất và ba giai đoạn**

Rửa tiền là quá trình hợp pháp hóa nguồn gốc của tài sản có được từ hành vi phạm tội. Về mặt nghiệp vụ, giới AML mô tả quá trình này qua ba giai đoạn kinh điển, và điều quan trọng với dự án là mỗi giai đoạn để lại một loại dấu vết khác nhau trên dữ liệu.

|**Giai đoạn**|**Bản chất**|**Dấu vết đặc trưng trên dữ liệu của fintech**|
|---|---|---|
|Sắp đặt<br>(Placement)|Đưa tiền bẩn vào hệ thống tài chính<br>chính thức: nộp tiền mặt, nạp ví,<br>mua thẻ trả trước, mua tài sản mã<br>hóa qua P2P.|Nhiều lần nạp tiền giá trị gần sát ngưỡng báo<br>cáo; nộp tiền tại nhiều điểm/nhiều chi nhánh<br>trong thời gian ngắn; tài khoản mới mở đã có<br>dòng tiền vào bất thường so với hồ sơ khách<br>hàng.|
|Phân tán<br>(Layering)|Cắt đứt liên hệ giữa tiền và tội<br>phạm nguồn bằng cách luân chuyển<br>qua nhiều tài khoản, nhiều tổ chức,<br>nhiều quốc gia, nhiều loại tài sản.|Chuỗi chuyển tiếp qua tài khoản trung gian, tiền<br>vào ra trong vài phút, số dư cuối ngày gần bằng<br>không, giao dịch vòng quay lại điểm xuất phát,<br>chia nhỏ rồi gộp lại.|
|Hợp nhất<br>(Integration)|Đưa tiền đã "sạch" trở lại nền kinh<br>tế dưới dạng tài sản hợp pháp: bất<br>động sản, doanh nghiệp, hợp đồng<br>dịch vụ, kiều hối.|Dòng tiền lớn ra khỏi hệ thống về pháp nhân<br>mới thành lập, thanh toán hợp đồng không tương<br>xứng năng lực doanh nghiệp, giao dịch với bên<br>liên quan.|



_Bảng 2.1 — Ba giai đoạn rửa tiền và dấu vết dữ liệu tương ứng._

Hệ quả thiết kế: một hệ thống chỉ chấm điểm từng giao dịch riêng lẻ sẽ nhìn thấy giai đoạn Sắp đặt tương đối tốt nhưng gần như mù trước giai đoạn Phân tán, vì giai đoạn Phân tán chỉ lộ diện khi ta nhìn quan hệ giữa nhiều tài khoản theo thời gian — tức là nhìn dưới dạng đồ thị, không phải dưới dạng bảng.

#### **2.2. Tội phạm nguồn phổ biến tại Việt Nam**

Theo cảnh báo của các cơ quan chức năng và diễn biến các vụ án lớn những năm gần đây, dòng tiền bẩn cần rửa tại Việt Nam chủ yếu đến từ: lừa đảo chiếm đoạt tài sản trên không gian mạng (giả mạo cơ quan chức năng, đầu tư tài chính/sàn ngoại hối giả, "việc nhẹ lương cao"), tổ chức đánh bạc và đánh bạc trực tuyến, tham nhũng và các sai phạm về phát hành trái phiếu/tín dụng, buôn lậu và vận chuyển trái phép tiền tệ qua biên giới, ma túy, và trốn thuế. Bộ Công an đã cảnh báo tình trạng thuê người Việt Nam mở tài khoản ngân hàng và lập công ty để rửa tiền cho các đường dây lừa đảo, chiếm đoạt tài sản.

Đặc điểm chung của các đường dây gần đây là quy mô tài khoản trung gian rất lớn (hàng nghìn tài khoản "mượn/thuê"), vòng đời mỗi tài khoản rất ngắn, và tốc độ luân chuyển tính bằng phút. Đây chính là đặc điểm khiến phương pháp điều tra thủ công theo từng cảnh báo không còn theo kịp.

#### **2.3. Danh mục mẫu hình (typology) trọng yếu cho FIN-07**

FIN-07 — Tài liệu phân tích nghiệp vụ AML | Nội bộ | Trang 4

Đây là danh mục mẫu hình mà hệ thống phải phát hiện được, sắp theo thứ tự ưu tiên triển khai. Cột "Dấu vết trên dữ liệu" chính là đặc trưng (feature) mà đội AI sẽ hiện thực hóa; cột cuối giải thích vì sao mắt người và luật cứng khó bắt được.

|**Mã**|**Mẫu hình**|**Cách thức**|**Dấu vết trên dữ liệu**|**Vì sao khó phát hiện thủ**<br>**công**|
|---|---|---|---|---|
|T01|Chia nhỏ giao<br>dịch<br>(Structuring /<br>Smurfing)|Cố ý chia một khoản<br>lớn thành nhiều<br>khoản dưới ngưỡng<br>báo cáo, phân bổ<br>theo thời gian hoặc<br>theo nhiều người<br>nộp.|Nhiều giao dịch có giá trị<br>nằm ngay dưới ngưỡng báo<br>cáo; tổng cộng dồn theo<br>cửa sổ 24h/7 ngày vượt<br>ngưỡng; độ lệch chuẩn của<br>số tiền rất nhỏ; giờ giao<br>dịch tập trung bất thường.|Từng giao dịch đơn lẻ<br>hoàn toàn hợp lệ. Chỉ lộ<br>ra khi cộng dồn đúng cửa<br>sổ thời gian và đúng<br>nhóm chủ thể liên quan.|
|T02|Mạng tài khoản<br>trung gian<br>(Money mule<br>network)|Thuê/mượn tài khoản<br>cá nhân làm điểm<br>trung chuyển; tiền<br>chỉ đi qua, không lưu<br>lại.|Tỷ lệ tiền ra/tiền vào ≈ 1;<br>thời gian lưu tiền rất ngắn;<br>số dư cuối ngày ≈ 0; tài<br>khoản mới mở, thiết bị/IP<br>dùng chung cho nhiều tài<br>khoản.|Mỗi tài khoản riêng lẻ chỉ<br>có vài giao dịch, không<br>đủ để bật cảnh báo. Mạng<br>lưới chỉ hiện ra khi ghép<br>nhiều tài khoản lại.|
|T03|Giao dịch vòng<br>(Circular /<br>Round-tripping<br>)|Tiền đi qua một<br>chuỗi tài khoản rồi<br>quay về chính chủ<br>thể ban đầu hoặc bên<br>liên quan.|Tồn tại chu trình có hướng<br>trong đồ thị giao dịch; tổng<br>giá trị chu trình lớn; độ trễ<br>giữa các bước ngắn và đều.|Không có công cụ đồ thị<br>thì phải dò tay từng bước;<br>chu trình dài 4–6 bước<br>gần như không thể phát<br>hiện bằng SQL thông<br>thường.|
|T04|Gom vào / Tỏa<br>ra (Fan-in /<br>Fan-out)|Nhiều nguồn nhỏ đổ<br>về một tài khoản<br>gom, rồi tài khoản<br>này tỏa ra nhiều đích.|Bậc vào (in-degree) hoặc<br>bậc ra (out-degree) tăng<br>đột biến trong thời gian<br>ngắn; tỷ lệ đối tác mới trên<br>tổng đối tác rất cao.|Ngưỡng cứng theo số tiền<br>không bắt được; phải nhìn<br>cấu trúc quan hệ và tốc độ<br>thay đổi của nó.|
|T05|Luân chuyển<br>tốc độ cao<br>(Rapid<br>pass-through)|Tiền vào và rút ra<br>gần như tức thời để<br>tối thiểu hóa khả<br>năng bị phong tỏa.|Chênh lệch thời gian<br>vào–ra tính bằng giây/phút;<br>doanh số ngày rất lớn<br>nhưng số dư rất nhỏ.|Cảnh báo sinh ra sau khi<br>tiền đã rời hệ thống; điều<br>tra thủ công luôn chậm<br>hơn dòng tiền.|
|T06|Rửa tiền qua<br>tài sản mã hóa|Chuyển sang tài sản<br>mã hóa qua kênh<br>P2P/OTC, dùng sàn<br>xuyên biên giới hoặc<br>dịch vụ trộn.|Đối tác thanh toán là<br>ví/điểm thu đổi đã biết; nội<br>dung chuyển khoản có từ<br>khóa; mẫu hình nạp–rút lặp<br>lại theo lô.|Phần lớn lưu lượng diễn<br>ra trên nền tảng xuyên<br>biên giới nằm ngoài tầm<br>quan sát của tổ chức trong<br>nước.|
|T07|Rửa tiền qua<br>đánh bạc trực<br>tuyến|Nạp tiền vào cổng<br>game/cá cược, rút ra<br>dưới danh nghĩa tiền<br>thắng cược.|Đối tác là các tài khoản<br>cổng trung gian; chu kỳ<br>nạp–rút ngắn và lặp; giao<br>dịch dày vào khung giờ<br>đêm.|Nhãn "cổng game" thay<br>đổi liên tục; danh sách đối<br>tác xấu luôn lạc hậu so<br>với thực tế.|



FIN-07 — Tài liệu phân tích nghiệp vụ AML | Nội bộ | Trang 5

|**Mã**|**Mẫu hình**|**Cách thức**|**Dấu vết trên dữ liệu**|**Vì sao khó phát hiện thủ**<br>**công**|
|---|---|---|---|---|
|T08|Rửa tiền qua<br>thương mại<br>(TBML)|Khai khống/khai<br>thiếu giá trị hàng<br>hóa, hóa đơn khống,<br>doanh nghiệp ma.|Doanh nghiệp mới thành<br>lập có doanh số bất tương<br>xứng; thanh toán không<br>khớp ngành nghề đăng ký;<br>đối tác nước ngoài rủi ro<br>cao.|Đòi hỏi đối chiếu dữ liệu<br>ngoài hệ thống (đăng ký<br>doanh nghiệp, hải quan)<br>mà phân tích viên hiếm<br>khi có thời gian tra cứu.|
|T09|Lợi dụng<br>khách hàng rủi<br>ro cao (PEP,<br>người có ảnh<br>hưởng chính<br>trị)|Sử dụng người thân,<br>người ủy quyền hoặc<br>pháp nhân trung gian<br>để che giấu chủ sở<br>hữu hưởng lợi.|Trùng khớp mờ với danh<br>sách PEP/trừng phạt; quan<br>hệ ủy quyền, đồng chủ tài<br>khoản; dòng tiền không<br>tương xứng thu nhập khai<br>báo.|Đối chiếu tên tiếng Việt<br>có dấu/không dấu, đảo<br>trật tự họ tên và bí danh<br>gây ra khối lượng khớp<br>sai khổng lồ.|
|T10|Chuyển tiền<br>không tương<br>xứng hồ sơ<br>khách hàng|Tài khoản cá nhân<br>phát sinh dòng tiền ở<br>quy mô doanh<br>nghiệp.|Độ lệch lớn giữa hành vi<br>thực tế và hồ sơ nghề<br>nghiệp/thu nhập; thay đổi<br>đột biến so với chính lịch<br>sử của khách hàng.|Ngưỡng chung cho toàn<br>tệp khách hàng vừa bỏ<br>sót, vừa gây báo động giả<br>cho nhóm khách hàng<br>hợp pháp có doanh số lớn.|



_Bảng 2.2 — Danh mục typology mục tiêu của FIN-07. Mã T01–T10 được dùng làm nhãn cho bộ luật phát hiện và bộ dữ liệu kiểm thử._

FIN-07 — Tài liệu phân tích nghiệp vụ AML | Nội bộ | Trang 6

## **3. PHÒNG, CHỐNG RỬA TIỀN TẠI VIỆT NAM — HIỆN TRẠNG (AS-IS)**

Chương này mô tả bức tranh hiện hành: ai làm gì, theo văn bản nào, quy trình chạy ra sao. Đây là bối cảnh bắt buộc, vì sản phẩm FIN-07 không thay thế cơ chế này mà phải khớp vào đúng các mắt xích của nó.

#### **3.1. Hệ thống văn bản pháp lý đang điều chỉnh**

|**Văn bản**|**Nội dung cốt lõi liên quan đến dự án**|
|---|---|
|Luật Phòng, chống rửa tiền<br>số 14/2022/QH15|Luật gốc: xác định đối tượng báo cáo (bao gồm tổ chức tài chính và trung<br>gian thanh toán), nghĩa vụ nhận biết khách hàng, danh mục dấu hiệu đáng<br>ngờ theo từng lĩnh vực, nghĩa vụ báo cáo giao dịch đáng ngờ, và các biện<br>pháp tạm thời gồm trì hoãn giao dịch, phong tỏa tài khoản, niêm phong<br>hoặc tạm giữ tài sản kèm điều kiện và thời hạn áp dụng.|
|Nghị định 19/2023/NĐ-CP|Quy định chi tiết một số điều của Luật: tiêu chí khách hàng rủi ro cao,<br>chủ sở hữu hưởng lợi, đánh giá rủi ro quốc gia, trách nhiệm các bộ ngành.|
|Thông tư<br>09/2023/TT-NHNN|Hướng dẫn thi hành: tiêu chí và phương pháp đánh giá rủi ro rửa tiền của<br>đối tượng báo cáo, quy trình quản lý rủi ro và phân loại khách hàng theo<br>mức độ rủi ro, quy định nội bộ về PCRT, chế độ báo cáo giao dịch giá trị<br>lớn, chế độ báo cáo giao dịch đáng ngờ, giao dịch chuyển tiền điện tử,<br>hình thức và thời hạn báo cáo dữ liệu điện tử. Mức giao dịch giá trị lớn<br>phải báo cáo là từ 400 triệu đồng trở lên.|
|Bộ luật Hình sự — tội Rửa<br>tiền|Cơ sở truy cứu trách nhiệm hình sự đối với hành vi hợp pháp hóa tài sản<br>do phạm tội mà có.|
|Quyết định 194/QĐ-TTg<br>(23/02/2024)|Kế hoạch hành động quốc gia thực hiện cam kết của Chính phủ với FATF<br>về phòng, chống rửa tiền — đặt ra các mốc và đầu việc cho từng bộ<br>ngành.|
|Nghị quyết 05/2025/NQ-CP<br>(09/9/2025)|Thí điểm thị trường tài sản mã hóa trong 5 năm; đặt tuân thủ AML/CFT<br>làm điều kiện nền để được cấp phép và tham gia thí điểm, kèm cơ chế<br>giám sát nhà cung cấp dịch vụ tài sản mã hóa (VASP).|
|Luật Bảo vệ dữ liệu cá nhân<br>số 91/2025/QH15 và Nghị<br>định 356/2025/NĐ-CP|Có hiệu lực từ 01/01/2026, thay thế Nghị định 13/2023/NĐ-CP. Ràng<br>buộc trực tiếp lên dự án: cơ sở pháp lý cho việc xử lý dữ liệu, thời hạn<br>phản hồi yêu cầu của chủ thể dữ liệu, lưu trữ bằng chứng đồng ý, quy<br>định chuyển dữ liệu ra ngoài, nghĩa vụ thông báo khi có vi phạm dữ liệu,<br>và yêu cầu chỉ định nhân sự/bộ phận bảo vệ dữ liệu cá nhân.|
|Chỉ đạo của NHNN về quản<br>lý rủi ro tài khoản thanh<br>toán|Yêu cầu các tổ chức tín dụng xây dựng và áp dụng thống nhất Bộ tiêu chí<br>nhận diện tài khoản thanh toán có dấu hiệu nghi ngờ gian lận, lừa đảo và<br>thường xuyên cập nhật bộ tiêu chí này.|



_Bảng 3.1 — Khung pháp lý nền cho FIN-07 (cập nhật tới 07/2026)._

#### **3.2. Bộ máy và vai trò của từng lực lượng**

Cơ chế phòng, chống rửa tiền của Việt Nam vận hành theo mô hình ba lớp: đối tượng báo cáo phát hiện và báo cáo — đơn vị tình báo tài chính phân tích và chuyển giao — cơ quan điều tra và tố tụng xử lý.

FIN-07 — Tài liệu phân tích nghiệp vụ AML | Nội bộ | Trang 7

|**Chủ thể**|**Vai trò trong chuỗi**|
|---|---|
|Đối tượng báo cáo<br>(ngân hàng, fintech, trung<br>gian thanh toán, chứng<br>khoán, bảo hiểm, casino,<br>kinh doanh BĐS, kim loại<br>quý…)|Nhận biết và cập nhật thông tin khách hàng; phân loại khách hàng theo<br>rủi ro; giám sát giao dịch; báo cáo giao dịch giá trị lớn và giao dịch đáng<br>ngờ; áp dụng biện pháp trì hoãn giao dịch khi có căn cứ; lưu trữ hồ sơ.|
|Cục Phòng, chống rửa tiền<br>— Ngân hàng Nhà nước|Đơn vị tình báo tài chính (FIU) quốc gia. Tiếp nhận báo cáo giao dịch<br>đáng ngờ (STR) và báo cáo giao dịch giá trị lớn; thu thập, phân tích, làm<br>giàu thông tin; chuyển giao thông tin cho cơ quan có thẩm quyền; giám<br>sát, cảnh báo và trao đổi thông tin với đối tác trong và ngoài nước.|
|Cơ quan Thanh tra, giám sát<br>ngân hàng — NHNN|Thanh tra, kiểm tra việc tuân thủ nghĩa vụ PCRT của đối tượng báo cáo;<br>xử phạt vi phạm hành chính.|
|Cục An ninh kinh tế và các<br>cục nghiệp vụ — Bộ Công<br>an|Tiếp nhận thông tin chuyển giao từ Cục PCRT, xác minh, điều tra tội<br>phạm nguồn và tội rửa tiền; đề nghị áp dụng biện pháp phong tỏa, kê<br>biên.|
|Viện kiểm sát, Tòa án|Truy tố, xét xử; quyết định tịch thu tài sản do phạm tội mà có.|
|Bộ Tài chính, UBCK, Hải<br>quan, Bộ Tư pháp, Bộ Công<br>Thương|Quản lý chuyên ngành đối với các nhóm đối tượng báo cáo phi ngân<br>hàng; kiểm soát vận chuyển tiền tệ qua biên giới.|



_Bảng 3.2 — Phân vai trong cơ chế PCRT quốc gia._

Ngày 27/11/2025, Cục Phòng, chống rửa tiền (NHNN) và Cục An ninh kinh tế (Bộ Công an) đã ký Quy chế phối hợp trong công tác xử lý thông tin giao dịch đáng ngờ, nhằm rút ngắn và chuẩn hóa khâu chuyển giao giữa hai đầu mối. Đây là tín hiệu cho thấy điểm nghẽn nằm ở chất lượng và tốc độ của hồ sơ chuyển giao, chứ không chỉ ở số lượng báo cáo.

#### **3.3. Quy trình nghiệp vụ hiện hành tại một tổ chức báo cáo**

Chuỗi công việc thực tế tại một fintech hoặc ngân hàng hiện nay diễn ra như sau:

- Bước 1 — Nhận biết khách hàng (CDD): thu thập và xác minh thông tin khi thiết lập quan hệ; áp dụng biện pháp tăng cường (EDD) với khách hàng rủi ro cao, khách hàng là cá nhân có ảnh hưởng chính trị, hoặc quan hệ liên quan tới quốc gia rủi ro cao.

- Bước 2 — Phân loại rủi ro khách hàng: chấm điểm theo các nhóm tiêu chí (khách hàng, sản phẩm/dịch vụ, kênh phân phối, vùng địa lý) và rà soát định kỳ theo mức rủi ro.

- Bước 3 — Giám sát giao dịch: hệ thống chạy bộ luật ngưỡng và kịch bản (scenario) trên dữ liệu giao dịch, sinh ra cảnh báo (alert). Song song, hệ thống lọc báo cáo giao dịch giá trị lớn theo ngưỡng 400 triệu đồng.

- Bước 4 — Sàng lọc cảnh báo tuyến 1 (L1): phân tích viên mở từng cảnh báo, đối chiếu hồ sơ khách hàng, lịch sử giao dịch, ghi nhận kết luận đóng cảnh báo hoặc chuyển tuyến 2.

FIN-07 — Tài liệu phân tích nghiệp vụ AML | Nội bộ | Trang 8

- Bước 5 — Điều tra tuyến 2 (L2): tra cứu quan hệ giữa các tài khoản, tìm giao dịch liên quan, đối chiếu danh sách trừng phạt/PEP, tổng hợp bằng chứng, viết bản tường thuật nghi vấn.

- Bước 6 — Phê duyệt và báo cáo: MLRO hoặc cấp có thẩm quyền phê duyệt; tổ chức lập và gửi báo cáo giao dịch đáng ngờ tới Cục PCRT theo mẫu và thời hạn quy định. Việc báo cáo giao dịch đáng ngờ không phụ thuộc vào số tiền giao dịch và không phụ thuộc giao dịch đã hoàn thành hay chưa.

- Bước 7 — Biện pháp tạm thời: khi có căn cứ theo luật, tổ chức áp dụng trì hoãn giao dịch; việc phong tỏa tài khoản hoặc niêm phong, tạm giữ tài sản tuân theo điều kiện và thời hạn luật định, thường gắn với yêu cầu của cơ quan nhà nước có thẩm quyền.

- Bước 8 — Lưu trữ và kiểm toán: lưu hồ sơ, dữ liệu và nhật ký để phục vụ thanh tra, kiểm toán nội bộ và cơ quan điều tra.

Toàn bộ chuỗi này hiện phụ thuộc rất nặng vào lao động thủ công ở Bước 4 và Bước 5 — và đó chính là nơi FIN-07 nhắm tới.

#### **3.4. Bối cảnh quốc tế và áp lực tuân thủ**

Việt Nam đưa ra cam kết cấp cao với FATF từ tháng 6/2023 và tính đến kỳ họp toàn thể tháng 6/2026 vẫn nằm trong nhóm quốc gia chịu tăng cường giám sát (thường gọi là "danh sách xám"). Hệ quả thực tế mà chính NHNN đã nêu bao gồm giảm sức hút đầu tư, chi phí vốn vay cao hơn và sự thận trọng của nhà đầu tư nước ngoài; nếu các thiếu hụt không được khắc phục còn có nguy cơ bị chuyển sang nhóm chịu biện pháp mạnh hơn.

Với một fintech, áp lực này chuyển hóa thành ba yêu cầu rất cụ thể: chất lượng báo cáo giao dịch đáng ngờ phải cao hơn (không chỉ nhiều hơn), phải chứng minh được hiệu quả của hệ thống giám sát chứ không chỉ chứng minh có hệ thống, và phải sẵn sàng giải trình từng quyết định trước thanh tra.

#### **3.5. Quy mô và nhịp độ hiện tại của hệ thống**

- Cục Phòng, chống rửa tiền cho biết từ khi Luật PCRT 2022 được ban hành, đơn vị tiếp nhận hàng nghìn báo cáo giao dịch đáng ngờ mỗi năm, với tốc độ tăng khoảng 30% qua các năm.

- Giai đoạn từ năm 2023 đến cuối năm 2025, Cục đã thực hiện thu thập, phân tích và ban hành gần 600 lượt văn bản liên quan đến hơn 5.000 giao dịch đáng ngờ chuyển giao cho Cục An ninh kinh tế.

- Trên bình diện ngành, các khảo sát quốc tế nhiều năm liền ghi nhận tỷ lệ báo động giả của hệ thống giám sát giao dịch theo luật cứng nằm trong khoảng 90–95% trở lên, nghĩa là phần lớn công sức của đội tuân thủ tiêu tốn vào những cảnh báo cuối cùng không dẫn tới đâu.

FIN-07 — Tài liệu phân tích nghiệp vụ AML | Nội bộ | Trang 9

Đặt cạnh nhau, ba con số trên cho thấy một nghịch lý: khối lượng báo cáo tăng nhanh, trong khi năng lực phân tích ở cả hai đầu — tổ chức báo cáo và cơ quan tiếp nhận — tăng chậm hơn nhiều. Đây là bối cảnh sinh ra nỗi đau mô tả ở Chương 4.

FIN-07 — Tài liệu phân tích nghiệp vụ AML | Nội bộ | Trang 10

## **4. PHÂN TÍCH NỖI ĐAU VÀ TUYÊN BỐ VẤN ĐỀ (PROBLEM STATEMENT)**

#### **4.1. Hành trình hiện tại của một cảnh báo (as-is journey)**

Để định vị nỗi đau chính xác, hãy theo dõi vòng đời điển hình của một cảnh báo trong hệ thống hiện nay:

|**Bước**|**Việc thực tế phải làm**|**Thời gian điển**<br>**hình**|**Điểm gãy**|
|---|---|---|---|
|1. Sinh cảnh<br>báo|Job chạy theo lô cuối ngày, đối<br>chiếu ngưỡng và kịch bản.|T+1|Tiền đã rời hệ thống trước khi cảnh<br>báo xuất hiện.|
|2. Xếp hàng|Cảnh báo vào hàng đợi, xếp theo<br>thời gian đến chứ không theo<br>mức độ nguy hiểm.|0,5–3 ngày|Cảnh báo nghiêm trọng nằm sau<br>hàng trăm cảnh báo vô hại.|
|3. Sàng lọc<br>L1|Mở hồ sơ khách hàng, xem sao<br>kê, tra Google, ghi kết luận.|10–40<br>phút/cảnh báo|Lặp lại thủ công; kết luận phụ<br>thuộc kinh nghiệm từng người.|
|4. Điều tra<br>L2|Truy vết dòng tiền nhiều bước,<br>dựng quan hệ giữa các tài khoản<br>bằng Excel, đối chiếu danh sách.|2 giờ – vài<br>ngày/vụ|Không có công cụ đồ thị; truy vết<br>quá 3 bước gần như bất khả thi.|
|5. Soạn hồ<br>sơ nghi vấn|Viết tường thuật, đính kèm bằng<br>chứng, điền biểu mẫu.|1–4 giờ/hồ sơ|Chất lượng không đồng đều; thiếu<br>trích dẫn bằng chứng chuẩn hóa.|
|6. Phê duyệt|MLRO đọc lại toàn bộ, yêu cầu<br>bổ sung, phê duyệt.|0,5–2 ngày|MLRO trở thành nút cổ chai; khó<br>kiểm chứng lại từng con số.|
|7. Lưu vết|Ghi nhật ký, lưu hồ sơ phục vụ<br>thanh tra.|rải rác|Nhật ký phân tán, không tái dựng<br>được đầy đủ diễn tiến quyết định.|



_Bảng 4.1 — Vòng đời cảnh báo hiện tại và các điểm gãy._

#### **4.2. Danh mục nỗi đau (Pain backlog)**

Mỗi nỗi đau được đánh mã để tham chiếu chéo sang backlog Jira. Cột "Bằng chứng/căn cứ" ghi nguồn quan sát; cột "Tác động" mô tả hệ quả nếu không giải quyết.

|**Mã**|**Nỗi đau**|**Nguyên nhân gốc**|**Tác động nếu không xử lý**|
|---|---|---|---|
|P01|Ngập trong báo động<br>giả — phần lớn cảnh<br>báo không dẫn tới hồ sơ<br>nghi vấn nào.|Luật cứng dùng ngưỡng chung<br>cho toàn tệp khách hàng, không<br>tính đến hành vi nền của từng<br>khách hàng.|Đội tuân thủ tiêu hao vào việc vô<br>ích; chi phí nhân sự tăng tuyến tính<br>theo lượng giao dịch; mệt mỏi cảnh<br>báo dẫn tới bỏ sót ca thật.|
|P02|Mù trước mạng lưới —<br>hệ thống chỉ thấy từng<br>tài khoản, không thấy<br>đường dây.|Dữ liệu được mô hình hóa dạng<br>bảng; không có biểu diễn đồ thị<br>và thuật toán tìm chu trình,<br>cộng đồng, đường đi.|Bỏ lọt toàn bộ nhóm typology T02,<br>T03, T04 — vốn là cách rửa tiền phổ<br>biến nhất hiện nay.|
|P03|Truy vết dòng tiền<br>nhiều bước quá tốn<br>công.|Phân tích viên phải tự viết truy<br>vấn hoặc ghép Excel cho từng<br>bước lan truyền.|Điều tra dừng ở bước 2–3; kết luận<br>thiếu chiều sâu; hồ sơ chuyển giao<br>yếu.|



FIN-07 — Tài liệu phân tích nghiệp vụ AML | Nội bộ | Trang 11

|**Mã**|**Nỗi đau**|**Nguyên nhân gốc**|**Tác động nếu không xử lý**|
|---|---|---|---|
|P04|Cảnh báo đến quá<br>muộn so với tốc độ<br>dòng tiền.|Xử lý theo lô cuối ngày; hàng<br>đợi không ưu tiên theo rủi ro.|Tiền đã rời hệ thống; biện pháp trì<br>hoãn giao dịch mất hiệu lực thực tế.|
|P05|Chất lượng điều tra phụ<br>thuộc từng cá nhân.|Không có quy trình chuẩn hóa<br>các bước điều tra; kiến thức<br>nằm trong đầu người có kinh<br>nghiệm.|Kết quả không nhất quán; rủi ro khi<br>nhân sự nghỉ việc; khó đào tạo<br>người mới.|
|P06|Soạn hồ sơ nghi vấn<br>tốn nhiều giờ và chất<br>lượng không đồng đều.|Viết tay từ đầu mỗi lần; bằng<br>chứng nằm rải rác ở nhiều hệ<br>thống.|Thời gian đáng lẽ dùng để điều tra<br>lại dùng để soạn thảo; cơ quan tiếp<br>nhận phải hỏi lại nhiều vòng.|
|P07|Đối chiếu danh sách<br>trừng phạt/PEP sinh ra<br>rất nhiều khớp sai với<br>tên tiếng Việt.|Trùng tên phổ biến; biến thể có<br>dấu/không dấu; đảo trật tự<br>họ–tên đệm–tên; bí danh.|Hoặc là bỏ sót đối tượng thật, hoặc<br>là chôn vùi đội ngũ trong hàng nghìn<br>khớp sai.|
|P08|Danh sách và tiêu chí<br>nhận diện luôn lạc hậu<br>so với thủ đoạn mới.|Cập nhật thủ công theo chu kỳ;<br>không có vòng phản hồi từ kết<br>quả điều tra về luật phát hiện.|Mỗi thủ đoạn mới cần hàng tháng<br>mới có luật tương ứng; giai đoạn<br>trống là giai đoạn thiệt hại.|
|P09|Không giải trình được<br>vì sao hệ thống kết luận<br>như vậy.|Điểm rủi ro sinh ra từ mô hình<br>hộp đen hoặc từ luật chồng<br>chéo không ghi lại lý do.|Không đáp ứng yêu cầu thanh tra;<br>không bảo vệ được quyết định trước<br>khiếu nại của khách hàng.|
|P10|Rủi ro AI bịa đặt liên<br>kết hoặc số liệu.|Mô hình ngôn ngữ sinh văn bản<br>trôi chảy kể cả khi không có dữ<br>liệu hậu thuẫn.|Một cáo buộc sai trong hồ sơ nghi<br>vấn gây thiệt hại pháp lý và uy tín<br>nghiêm trọng — đây là rủi ro tồn<br>vong của sản phẩm.|
|P11|Nhật ký kiểm toán phân<br>tán, không tái dựng<br>được diễn tiến quyết<br>định.|Mỗi hệ thống ghi log riêng;<br>không có mã vụ việc xuyên<br>suốt.|Thanh tra không xác minh được;<br>tranh chấp nội bộ không có căn cứ.|
|P12|Xung đột giữa nhu cầu<br>phân tích dữ liệu và<br>nghĩa vụ bảo vệ dữ liệu<br>cá nhân.|Luật BVDLCN 2025 và Nghị<br>định 356/2025 siết chặt cơ sở<br>xử lý, lưu trữ và chuyển giao dữ<br>liệu.|Nguy cơ vi phạm khi đưa dữ liệu<br>khách hàng ra dịch vụ bên ngoài<br>hoặc lưu trữ vượt mục đích.|
|P13|Rủi ro lộ lọt thông tin<br>điều tra (tipping-off).|Quyền truy cập rộng; thông báo<br>tự động có thể chạm tới người<br>bị điều tra.|Đối tượng tẩu tán tài sản; vi phạm<br>nghĩa vụ giữ bí mật điều tra.|
|P14|Không đo được hiệu<br>quả của chính hệ thống<br>giám sát.|Thiếu chỉ số về tỷ lệ chuyển đổi<br>cảnh báo thành hồ sơ, thời gian<br>xử lý, tỷ lệ bỏ sót.|Không biết nên đầu tư vào đâu;<br>không chứng minh được hiệu quả<br>với cơ quan quản lý.|



_Bảng 4.2 — Danh mục nỗi đau P01–P14, dùng làm nguồn truy vết cho toàn bộ backlog._

#### **4.3. Nỗi đau nhìn từ từng vai trò (persona)**

FIN-07 — Tài liệu phân tích nghiệp vụ AML | Nội bộ | Trang 12

|**Vai trò**|**Việc cần hoàn**<br>**thành**|**Nỗi đau lớn nhất**|**Kỳ vọng với FIN-07**|
|---|---|---|---|
|Phân tích viên<br>tuyến 1|Xử lý hết hàng đợi<br>cảnh báo trong ngày<br>với kết luận có căn<br>cứ.|Khối lượng cảnh báo vô<br>nghĩa; lặp đi lặp lại thao tác<br>tra cứu (P01, P03).|Cảnh báo được xếp hạng theo<br>rủi ro, kèm sẵn bối cảnh và<br>bằng chứng để quyết định<br>trong vài phút.|
|Điều tra viên<br>tuyến 2|Dựng lại bức tranh<br>dòng tiền và xác định<br>đường dây.|Không có công cụ đồ thị;<br>truy vết quá 3 bước là bất<br>khả thi (P02, P03).|Đồ thị giao dịch tương tác, tự<br>động phát hiện chu trình và<br>cụm, xuất được bằng chứng.|
|MLRO / Trưởng<br>bộ phận tuân thủ|Ra quyết định báo<br>cáo hoặc không, chịu<br>trách nhiệm trước<br>pháp luật.|Phải tin vào hồ sơ mà mình<br>không kiểm chứng lại được<br>từng con số (P06, P09, P10).|Mọi câu trong hồ sơ đều dẫn<br>được về bản ghi gốc; có nút<br>phê duyệt/từ chối kèm lý do<br>được lưu vết.|
|Kiểm toán nội<br>bộ & thanh tra|Xác minh tổ chức đã<br>tuân thủ đúng quy<br>trình.|Nhật ký phân tán, không tái<br>dựng được (P11).|Một dòng thời gian duy nhất<br>cho mỗi vụ việc, bất biến, xuất<br>được ra hồ sơ.|
|Ban lãnh đạo /<br>CTO|Kiểm soát chi phí<br>tuân thủ và rủi ro<br>pháp lý.|Chi phí tăng theo lượng giao<br>dịch mà hiệu quả không đo<br>được (P14).|Bảng chỉ số hiệu quả: tỷ lệ<br>chuyển đổi cảnh báo, thời gian<br>xử lý trung bình, tỷ lệ báo<br>động giả.|
|Khách hàng<br>ngay tình|Giao dịch bình<br>thường không bị gián<br>đoạn.|Bị chặn nhầm, phải giải<br>trình, không được biết lý do.|Giảm chặn nhầm; quyết định<br>có căn cứ và có thể giải thích.|



_Bảng 4.3 — Bản đồ persona._

#### **4.4. Định lượng nỗi đau (mô hình minh họa)**

Mô hình dưới đây dùng giả định của một fintech tầm trung để biến nỗi đau thành con số. Các giả định được nêu rõ để nhóm có thể thay bằng số liệu thật khi có dữ liệu của tổ chức tiếp nhận sản phẩm.

|**Chỉ số**|**Giả định / cách tính**|**Giá trị minh họa**|
|---|---|---|
|Số giao dịch mỗi tháng|Giả định đầu vào|20.000.000|
|Tỷ lệ sinh cảnh báo|Giả định 0,05% giao dịch bật luật|10.000 cảnh báo/tháng|
|Tỷ lệ báo động giả|Theo mức phổ biến của hệ thống luật<br>cứng, 90–95%|≈ 9.000–9.500 cảnh báo vô<br>ích/tháng|
|Thời gian sàng lọc L1 trung<br>bình|Giả định 20 phút/cảnh báo|≈ 3.333 giờ công/tháng|
|Quy đổi nhân sự|160 giờ/người/tháng|≈ 20 phân tích viên chỉ để giữ<br>hàng đợi không tràn|
|Thời gian soạn một hồ sơ<br>nghi vấn|Giả định 3 giờ|3 giờ × số hồ sơ/tháng|



FIN-07 — Tài liệu phân tích nghiệp vụ AML | Nội bộ | Trang 13

|**Chỉ số**|**Giả định / cách tính**|**Giá trị minh họa**|
|---|---|---|
|Mục tiêu của FIN-07|Giảm 60% khối lượng sàng lọc thủ công<br>và 50% thời gian soạn hồ sơ|Giải phóng ≈ 2.000 giờ<br>công/tháng để dùng cho điều<br>tra thực chất|



_Bảng 4.4 — Mô hình định lượng minh họa. Mọi con số là giả định để phục vụ lập luận, cần thay bằng số liệu thật trước khi đưa vào hồ sơ đầu tư._

#### **4.5. Tuyên bố vấn đề**

Bộ phận tuân thủ của các fintech Việt Nam đang phải giám sát một khối lượng giao dịch tăng nhanh bằng những hệ thống dựa trên ngưỡng cứng vốn sinh ra 90–95% báo động giả, đồng thời lại không nhìn thấy được các cấu trúc rửa tiền thực sự nguy hiểm — mạng tài khoản trung gian, giao dịch vòng, chia nhỏ có phối hợp — vì các cấu trúc này chỉ hiện ra ở cấp độ mạng lưới chứ không ở cấp độ từng giao dịch. Hệ quả là phân tích viên tiêu hao phần lớn thời gian vào việc đóng những cảnh báo vô hại, việc điều tra sâu bị bỏ dở ở bước thứ hai hoặc thứ ba, hồ sơ nghi vấn được soạn thủ công mất nhiều giờ và chất lượng không đồng đều, còn tổ chức thì không giải trình được vì sao hệ thống kết luận như vậy khi thanh tra hỏi tới.

FIN-07 đặt mục tiêu thu hẹp đúng khoảng trống đó: một AI Agent giám sát AML biết tự phân tích mạng lưới giao dịch, tự thực hiện các bước điều tra theo quy trình chuẩn hóa, tự tổng hợp hồ sơ nghi vấn trong đó mỗi khẳng định đều gắn với bản ghi dữ liệu gốc, và luôn dừng lại chờ con người phê duyệt trước mọi hành động có hậu quả pháp lý.

Ràng buộc bất di bất dịch: hệ thống không được phép suy diễn liên kết hay số liệu không có trong dữ liệu; mọi cáo buộc phải dẫn được về bằng chứng; mọi quyết định phải để lại dấu vết kiểm toán; và không hành động nào ảnh hưởng tới tài khoản khách hàng hay tới cơ quan quản lý được thực hiện mà thiếu phê duyệt của người có thẩm quyền.

FIN-07 — Tài liệu phân tích nghiệp vụ AML | Nội bộ | Trang 14

## **5. TỪ NỖI ĐAU ĐẾN NĂNG LỰC SẢN PHẨM**

#### **5.1. Ánh xạ nỗi đau — năng lực**

|**Nỗi đau**|**Năng lực cần có**|**Thành phần kỹ thuật**|
|---|---|---|
|P01, P10|Chấm điểm rủi ro theo hành vi nền của<br>từng khách hàng thay vì ngưỡng chung;<br>xếp hạng hàng đợi theo mức nguy hiểm.|Mô hình phát hiện bất thường (Isolation<br>Forest / Autoencoder) + bộ luật typology +<br>lớp hợp nhất điểm.|
|P02, P03|Dựng đồ thị giao dịch, phát hiện chu<br>trình, cụm, tài khoản trung chuyển,<br>đường lan truyền nhiều bước.|NetworkX: tìm chu trình có hướng, phát hiện<br>cộng đồng, các chỉ số trung tâm, truy vết<br>k-hop.|
|P04|Rút ngắn độ trễ phát hiện và ưu tiên xử<br>lý theo rủi ro.|Pipeline theo lô ngắn hạn + hàng đợi ưu tiên<br>theo điểm rủi ro.|
|P05, P06|Chuẩn hóa quy trình điều tra và tự động<br>soạn thảo bản tường thuật nghi vấn.|LangGraph điều phối các bước điều tra cố<br>định; mẫu hồ sơ theo cấu trúc quy định.|
|P07|Đối chiếu danh sách trừng phạt/PEP<br>chịu được biến thể tên tiếng Việt.|Vector DB kết hợp chuẩn hóa tên, so khớp<br>mờ và ngưỡng tin cậy phân tầng.|
|P08|Vòng phản hồi từ kết quả phê duyệt về<br>lại bộ luật và mô hình.|Lưu nhãn kết luận của người duyệt; báo cáo<br>hiệu quả từng luật theo thời gian.|
|P09, P10, P11|Mọi khẳng định gắn với bằng chứng;<br>mọi bước để lại nhật ký bất biến.|Lớp trích dẫn bằng chứng bắt buộc; kiểm tra<br>tự động chặn phát biểu không có nguồn;<br>bảng nhật ký chỉ ghi thêm.|
|P12, P13|Tối thiểu hóa dữ liệu, phân quyền theo<br>vai trò, che dữ liệu nhạy cảm.|Kiểm soát truy cập theo vai trò, che/ẩn dữ<br>liệu định danh, chính sách lưu trữ theo mục<br>đích.|
|P14|Đo hiệu quả của chính hệ thống.|Bảng chỉ số: tỷ lệ chuyển đổi cảnh báo, thời<br>gian xử lý, tỷ lệ báo động giả, độ phủ<br>typology.|



_Bảng 5.1 — Ánh xạ nỗi đau sang năng lực và thành phần kỹ thuật._

#### **5.2. Kiến trúc nghiệp vụ của agent điều tra**

Agent được thiết kế như một quy trình điều tra có trạng thái, không phải một hộp chat. Mỗi nút là một bước nghiệp vụ có đầu vào, đầu ra và bằng chứng rõ ràng:

- Nút Tiếp nhận: nhận cảnh báo, chuẩn hóa bối cảnh khách hàng và khoảng thời gian điều tra.

- Nút Truy hồi bằng chứng: gọi công cụ truy vấn dữ liệu để lấy giao dịch, đối tác, hồ sơ khách hàng — mọi số liệu chỉ đến từ đây, không đến từ trí nhớ của mô hình.

- Nút Phân tích đồ thị: dựng đồ thị quanh chủ thể, chạy các thuật toán phát hiện chu trình, cụm, tài khoản trung chuyển.

- Nút Đối chiếu danh sách: sàng lọc các bên liên quan với danh sách trừng phạt và PEP, trả về mức độ khớp kèm căn cứ.

FIN-07 — Tài liệu phân tích nghiệp vụ AML | Nội bộ | Trang 15

- Nút Tính toán: dùng công cụ mã (code tool) để tính tổng, ngưỡng, tỷ lệ — không để mô hình ngôn ngữ tự tính số.

- Nút Lập luận và kết luận: tổng hợp các bằng chứng thành nhận định, gán typology, đề xuất mức độ nghi vấn.

- Nút Soạn hồ sơ: sinh bản tường thuật theo cấu trúc, mỗi câu khẳng định gắn mã bằng chứng.

- Nút Kiểm chứng: kiểm tra tự động rằng không có khẳng định nào thiếu bằng chứng và không có số liệu nào lệch so với nguồn; nếu phát hiện, trả lại nút trước.

- Nút Chờ người (HITL): dừng hoàn toàn, chuyển hồ sơ cho người có thẩm quyền phê duyệt, từ chối hoặc yêu cầu điều tra bổ sung. Không có nhánh nào cho phép vượt qua nút này.

#### **5.3. Nguyên tắc thiết kế bắt buộc**

|**Nguyên tắc**|**Diễn giải thành yêu cầu kiểm thử được**|
|---|---|
|Bằng chứng là bắt buộc|Mọi câu trong hồ sơ nghi vấn phải tham chiếu ít nhất một mã bản ghi. Hồ sơ<br>chứa câu không có tham chiếu sẽ bị hệ thống chặn, không cho chuyển sang<br>bước phê duyệt.|
|Không tự tính số|Mọi con số trong hồ sơ phải khớp tuyệt đối với kết quả trả về từ công cụ truy<br>vấn hoặc công cụ tính toán. Kiểm thử tự động so khớp từng số.|
|Con người quyết định<br>cuối cùng|Không có đường dẫn nào trong hệ thống dẫn tới hành động phong tỏa tài<br>khoản hoặc phát hành báo cáo ra ngoài mà không đi qua thao tác phê duyệt<br>của người dùng có vai trò tương ứng.|
|Ghi vết bất biến|Mọi truy vấn, mọi kết luận của agent, mọi thao tác của người dùng đều ghi<br>vào nhật ký chỉ-ghi-thêm, gắn mã vụ việc, dấu thời gian và danh tính người<br>thực hiện.|
|Tối thiểu hóa dữ liệu|Agent chỉ được truy cập trường dữ liệu cần cho bước hiện tại; dữ liệu định<br>danh được che khi hiển thị cho vai trò không cần biết.|
|Giữ bí mật điều tra|Không có kênh thông báo nào từ hệ thống tới khách hàng bị điều tra; quyền<br>xem vụ việc giới hạn theo vai trò và theo phân công.|
|Giải thích được|Mỗi điểm rủi ro phải kèm danh sách yếu tố đóng góp và trọng số, hiển thị<br>được cho phân tích viên và cho kiểm toán.|
|Giảm báo động giả có<br>kiểm soát|Mọi thay đổi làm giảm cảnh báo phải kèm báo cáo ảnh hưởng: bao nhiêu ca<br>thật bị mất trên tập kiểm thử có nhãn.|



_Bảng 5.2 — Nguyên tắc thiết kế và cách kiểm chứng._

FIN-07 — Tài liệu phân tích nghiệp vụ AML | Nội bộ | Trang 16

## **6. PHẠM VI SẢN PHẨM CHO 5 TUẦN**

#### **6.1. Trong phạm vi (MVP)**

- Bộ dữ liệu giao dịch mô phỏng có nhãn, cài sẵn các typology T01–T05 và T09 để phục vụ huấn luyện và đo lường.

- Bộ luật phát hiện theo ngưỡng và kịch bản, cấu hình được, có ghi lý do bật cảnh báo.

- Mô hình phát hiện bất thường theo hành vi nền của khách hàng, có lớp giải thích yếu tố đóng góp.

- Mô-đun đồ thị: dựng đồ thị, tìm chu trình, phát hiện cụm, xác định tài khoản trung chuyển, truy vết nhiều bước.

- Mô-đun đối chiếu danh sách trừng phạt/PEP với so khớp mờ cho tên tiếng Việt.

- Agent điều tra theo quy trình cố định, có công cụ truy vấn dữ liệu và công cụ tính toán, sinh hồ sơ nghi vấn có trích dẫn bằng chứng.

- Quy trình phê duyệt có con người, phân vai phân tích viên và người phê duyệt, kèm nhật ký kiểm toán.

- Giao diện web: hàng đợi cảnh báo, hồ sơ vụ việc, đồ thị tương tác, màn hình rà soát và phê duyệt hồ sơ nghi vấn, bảng chỉ số.

- Triển khai lên môi trường cloud, có CI/CD, giám sát và sao lưu.

#### **6.2. Ngoài phạm vi lần này**

- Kết nối trực tiếp tới hệ thống báo cáo của cơ quan quản lý; bản MVP chỉ xuất hồ sơ ra tệp theo cấu trúc.

- Xử lý luồng thời gian thực dưới một giây và tích hợp core banking thật.

- Tự động thực hiện phong tỏa tài khoản — hệ thống chỉ tạo đề xuất, việc thực thi nằm ngoài sản phẩm.

- eKYC, phát hiện gian lận thanh toán, chấm điểm tín dụng.

- Dữ liệu khách hàng thật; toàn bộ giai đoạn phát triển dùng dữ liệu mô phỏng hoặc dữ liệu đã ẩn danh.

## **7. TIÊU CHÍ THÀNH CÔNG**

|**Nhóm**|**Chỉ số**|**Mục tiêu MVP**|**Cách đo**|
|---|---|---|---|
|Chất lượng phát<br>hiện|Độ phủ typology trên tập kiểm<br>thử có nhãn|≥ 85% với T01–T05|Chạy trên bộ dữ liệu<br>mô phỏng có nhãn|
|Chất lượng phát<br>hiện|Tỷ lệ báo động giả so với đường<br>cơ sở luật cứng|Giảm ≥ 50%|So sánh cùng tập dữ<br>liệu, cùng ngưỡng cảnh<br>báo|



FIN-07 — Tài liệu phân tích nghiệp vụ AML | Nội bộ | Trang 17

|**Nhóm**|**Chỉ số**|**Mục tiêu MVP**|**Cách đo**|
|---|---|---|---|
|Tính trung thực|Tỷ lệ câu khẳng định có trích dẫn<br>bằng chứng hợp lệ|100%|Kiểm tra tự động trên<br>toàn bộ hồ sơ sinh ra|
|Tính trung thực|Sai lệch số liệu giữa hồ sơ và<br>nguồn dữ liệu|0 trường hợp|So khớp tự động từng<br>số|
|Hiệu suất|Thời gian agent hoàn tất một vụ<br>điều tra|≤ 3 phút/vụ|Đo trên môi trường<br>staging|
|Hiệu suất|Thời gian dựng và hiển thị đồ thị<br>5.000 nút|≤ 5 giây|Đo phía giao diện|
|Tuân thủ|Tỷ lệ hành động nhạy cảm có<br>bản ghi phê duyệt|100%|Đối soát nhật ký kiểm<br>toán|
|Tuân thủ|Khả năng tái dựng đầy đủ diễn<br>tiến một vụ việc|Đạt|Diễn tập kiểm toán nội<br>bộ|
|Trải nghiệm|Thời gian phân tích viên xử lý<br>một cảnh báo|Giảm ≥ 40% so với quy<br>trình thủ công|Đo thời gian trên phiên<br>thử nghiệm người dùng|



_Bảng 7.1 — Bộ tiêu chí nghiệm thu._

## **8. RỦI RO, GIẢ ĐỊNH VÀ PHỤ THUỘC**

|**Mã**|**Rủi ro / giả định**|**Mức**|**Biện pháp**|
|---|---|---|---|
|R01|Mô hình ngôn ngữ sinh ra liên kết<br>hoặc số liệu không có thật.|Rất cao|Bắt buộc trích dẫn bằng chứng; nút<br>kiểm chứng tự động; mọi phép tính do<br>công cụ mã thực hiện; kiểm thử đối<br>kháng cho tình huống dữ liệu rỗng.|
|R02|Không có dữ liệu giao dịch thật để<br>huấn luyện và đánh giá.|Cao|Xây bộ sinh dữ liệu mô phỏng có nhãn<br>ngay tuần 1; công bố rõ giới hạn của kết<br>quả đo.|
|R03|Đồ thị lớn gây chậm khi dựng và hiển<br>thị.|Trung bình|Giới hạn cửa sổ thời gian và số bước lan<br>truyền; tính trước các chỉ số; phân trang<br>và gom cụm ở tầng giao diện.|
|R04|Đối chiếu tên tiếng Việt sinh quá<br>nhiều khớp sai.|Cao|Chuẩn hóa dấu và trật tự tên; ngưỡng tin<br>cậy phân tầng; luôn hiển thị căn cứ<br>khớp cho người rà soát.|
|R05|Yêu cầu bảo vệ dữ liệu cá nhân làm<br>hẹp phạm vi dữ liệu dùng được.|Trung bình|Dùng dữ liệu mô phỏng trong toàn bộ<br>dự án; thiết kế tối thiểu hóa dữ liệu ngay<br>từ mô hình dữ liệu.|
|R06|5 tuần là khung thời gian rất ngắn cho<br>phạm vi đề ra.|Cao|Cắt phạm vi theo lát dọc chạy được từ<br>tuần 2; ưu tiên T01–T03 trước; các<br>typology còn lại là hạng mục có thể cắt.|
|R07|Nhóm chỉ có một kỹ sư AI cho cả mô<br>hình, đồ thị và agent.|Cao|Backend chia sẻ phần công cụ truy vấn<br>và tính toán; PM giữ vai trò rà soát chất<br>lượng bằng chứng.|



FIN-07 — Tài liệu phân tích nghiệp vụ AML | Nội bộ | Trang 18

|**Mã**|**Rủi ro / giả định**|**Mức**|**Biện pháp**|
|---|---|---|---|
|R08|Giả định: quy trình phê duyệt hai cấp<br>(phân tích viên và người phê duyệt) là<br>đủ cho MVP.|Giả định|Xác nhận với MLRO trước cuối tuần 2;<br>nếu cần ba cấp, mở rộng bảng vai trò.|



_Bảng 8.1 — Đăng ký rủi ro ban đầu._

FIN-07 — Tài liệu phân tích nghiệp vụ AML | Nội bộ | Trang 19

## **PHỤ LỤC A — DẤU HIỆU ĐÁNG NGỜ TRONG LĨNH VỰC NGÂN HÀNG**

Luật Phòng, chống rửa tiền 2022 liệt kê nhóm dấu hiệu đáng ngờ riêng cho lĩnh vực ngân hàng bên cạnh nhóm dấu hiệu cơ bản áp dụng chung. Dưới đây là bản diễn giải nghiệp vụ theo cách hiểu của nhóm dự án, dùng để đối chiếu khi thiết kế bộ luật phát hiện; bản gốc đầy đủ cần tra cứu trực tiếp văn bản luật.

- Biến động đột ngột về doanh số trên tài khoản; tiền vào và rút ra rất nhanh; doanh số trong ngày lớn nhưng số dư còn lại rất nhỏ hoặc bằng không.

- Nhiều khoản chuyển giá trị nhỏ từ nhiều tài khoản dồn về một tài khoản hoặc theo chiều ngược lại trong thời gian ngắn; tiền đi qua nhiều tài khoản; các bên không quan tâm tới phí giao dịch; thực hiện nhiều giao dịch mà mỗi giao dịch đều ở mức gần sát ngưỡng phải báo cáo.

- Giao dịch không phù hợp với hoạt động kinh doanh hoặc với hồ sơ, thu nhập đã khai báo của khách hàng.

- Khách hàng cung cấp thông tin nhận biết không chính xác, không đầy đủ, hoặc trì hoãn cung cấp một cách bất thường.

- Tài khoản không phát sinh giao dịch trong thời gian dài bỗng hoạt động trở lại với dòng tiền lớn.

- Giao dịch liên quan tới cá nhân, tổ chức hoặc quốc gia thuộc nhóm rủi ro cao, hoặc liên quan tới danh sách cảnh báo.

- Dấu hiệu cho thấy khách hàng thực hiện giao dịch thay cho người khác mà không giải trình được lý do.

Nhóm dự án ánh xạ mỗi dấu hiệu trên thành một hoặc nhiều luật phát hiện có mã riêng, để khi cảnh báo bật lên, hồ sơ ghi rõ dấu hiệu luật định tương ứng — đây là điều kiện để hồ sơ nghi vấn có giá trị trước cơ quan quản lý.

## **PHỤ LỤC B — THUẬT NGỮ**

|**Thuật ngữ**|**Giải thích**|
|---|---|
|AML / CFT|Phòng, chống rửa tiền / chống tài trợ khủng bố.|
|CDD / EDD|Nhận biết khách hàng ở mức tiêu chuẩn / ở mức tăng cường đối với khách hàng<br>rủi ro cao.|
|STR / SAR|Báo cáo giao dịch đáng ngờ gửi cơ quan có thẩm quyền.|
|CTR|Báo cáo giao dịch có giá trị lớn phải báo cáo (ngưỡng hiện hành từ 400 triệu<br>đồng).|
|PEP|Cá nhân có ảnh hưởng chính trị và người liên quan.|



FIN-07 — Tài liệu phân tích nghiệp vụ AML | Nội bộ | Trang 20

|**Thuật ngữ**|**Giải thích**|
|---|---|
|FIU|Đơn vị tình báo tài chính quốc gia — tại Việt Nam là Cục Phòng, chống rửa tiền<br>thuộc NHNN.|
|FATF / APG|Lực lượng đặc nhiệm tài chính về chống rửa tiền và Nhóm châu Á – Thái Bình<br>Dương về chống rửa tiền.|
|MLRO|Cán bộ chịu trách nhiệm về phòng, chống rửa tiền của tổ chức.|
|HITL|Có con người trong vòng lặp quyết định — bắt buộc trước mọi hành động có hậu<br>quả pháp lý.|
|Typology|Mẫu hình thủ đoạn rửa tiền đã được nhận diện và mô tả.|
|Structuring|Chia nhỏ giao dịch để né ngưỡng báo cáo.|
|Mule account|Tài khoản trung gian được mượn hoặc thuê để trung chuyển dòng tiền.|
|Tipping-off|Làm lộ việc một khách hàng đang bị điều tra — hành vi bị cấm.|
|VASP|Tổ chức cung cấp dịch vụ tài sản mã hóa.|



## **PHỤ LỤC C — NGUỒN THAM KHẢO**

- Luật Phòng, chống rửa tiền số 14/2022/QH15; Nghị định 19/2023/NĐ-CP; Thông tư 09/2023/TT-NHNN.

- Luật Bảo vệ dữ liệu cá nhân số 91/2025/QH15 và Nghị định 356/2025/NĐ-CP (hiệu lực 01/01/2026).

- Nghị quyết 05/2025/NQ-CP ngày 09/9/2025 về thí điểm thị trường tài sản mã hóa.

- Quyết định 194/QĐ-TTg ngày 23/02/2024 ban hành kế hoạch hành động quốc gia thực hiện cam kết với FATF.

- FATF — Danh sách các quốc gia chịu tăng cường giám sát, kỳ họp toàn thể tháng 6/2026 (Việt Nam vẫn trong danh sách).

- APG — Báo cáo đánh giá đa phương vòng ba đối với Việt Nam (2022).

- Thông tin từ Hội nghị ký Quy chế phối hợp giữa Cục Phòng, chống rửa tiền (NHNN) và Cục An ninh kinh tế (Bộ Công an), ngày 27/11/2025.

- Các khảo sát ngành về tỷ lệ báo động giả trong giám sát giao dịch AML (2024–2026).

**— HẾT —**

FIN-07 — Tài liệu phân tích nghiệp vụ AML | Nội bộ | Trang 21
