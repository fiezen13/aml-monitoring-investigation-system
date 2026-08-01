import type { Approval, SarDraft } from "../types";

/**
 * SAR-2026-007 — bản nháp trung tâm của luồng demo, sinh từ CASE-2026-014.
 * Ba lỗi kiểm chứng ban đầu khớp screenshot "Bản nháp SAR-2026-007".
 */
export const SAR_DRAFT: SarDraft = {
  sar_id: "SAR-2026-007",
  case_id: "CASE-2026-014",
  alert_id: "ALT-2026-001",
  status: "DRAFT",
  suspicionType: "Cấu trúc giao dịch (Structuring) - Chia nhỏ số tiền để tránh ngưỡng báo cáo.",
  riskLevel: "CAO",
  subjectName: "Nguyễn Thành Nam",
  submittedBy: "Nguyễn Quang Hưng",
  submittedByRole: "Compliance Officer",
  behaviourSummary:
    "Khách hàng Nguyễn Thành Nam thực hiện 14 giao dịch nộp tiền mặt tại 3 chi nhánh khác nhau trong vòng 95 phút. 82% các khoản nộp đơn lẻ có giá trị sát dưới ngưỡng báo cáo. Tổng giá trị lũy kế 1.372.000.000 VNĐ, trong đó 74% đối tác là đối tác mới. Hành vi này có dấu hiệu của kỹ thuật Smurfing/Structuring nhằm tránh sự giám sát của cơ quan quản lý. Sau khi nộp tiền, toàn bộ số dư được chuyển ra nước ngoài thông qua lệnh chuyển tiền SWIFT.",
  statements: [
    {
      id: "st-1",
      text: "14 giao dịch nộp tiền mặt được thực hiện trong 95 phút tại 3 chi nhánh khác nhau.",
      evidenceIds: ["EV-00031", "EV-00052"],
      highlight: "TRX-892731-EXT",
    },
    {
      id: "st-2",
      text: "82% giao dịch có giá trị sát dưới ngưỡng báo cáo bắt buộc (Threshold Pattern).",
      evidenceIds: ["EV-00052"],
    },
    {
      id: "st-3",
      text: "Chủ thể có liên kết sở hữu gián tiếp với CTY TNHH Blue Ocean qua một pháp nhân trung gian.",
      evidenceIds: ["EV-00045"],
    },
  ],
  inflow: 1372000000,
  outflow: 1370500000,
  inflowNote: "Tiền mặt",
  outflowNote: "Quốc tế",
  validationIssues: [
    {
      id: "iss-1",
      severity: "error",
      title: "Thiếu định danh SWIFT",
      detail: "Lệnh chuyển ngày 12/05 chưa có mã BIC hợp lệ.",
    },
    {
      id: "iss-2",
      severity: "error",
      title: "Xác thực KYC hết hạn",
      detail: "Căn cước công dân của Nguyễn Thành Nam đã hết hạn từ 01/2026.",
    },
    {
      id: "iss-3",
      severity: "warning",
      title: "Cảnh báo liên đới",
      detail: "Địa chỉ IP thực hiện lệnh trùng với 1 hồ sơ SAR cũ năm 2024.",
    },
  ],
  relatedTransactions: [
    {
      transaction_id: "TRX-892731",
      time: "20/05/2026 09:12",
      amount: "195,000,000 VNĐ",
      location: "CN Quận 1, TP.HCM",
    },
    {
      transaction_id: "TRX-892735",
      time: "20/05/2026 10:45",
      amount: "188,500,000 VNĐ",
      location: "CN Quận 3, TP.HCM",
    },
    {
      transaction_id: "TRX-892742",
      time: "20/05/2026 14:20",
      amount: "192,000,000 VNĐ",
      location: "CN Biên Hòa, ĐN",
    },
  ],
  networkConfidence: 92,
  history: [
    {
      time: "21/05/2026 08:30",
      text: "Báo cáo hoàn tất Validation",
      actor: "Hệ thống tự động",
    },
    {
      time: "20/05/2026 17:15",
      text: "Đã trình MLRO phê duyệt",
      actor: "Nguyễn Văn An (Analyst)",
    },
  ],
};

/** Hàng đợi phê duyệt — khớp screenshot "Hàng đợi Phê duyệt SAR". */
export const APPROVALS: Approval[] = [
  {
    sar_id: "SAR-2026-008",
    sender: "Nguyễn Hoàng",
    senderRole: "Senior Analyst",
    status: "pending",
    statusLabel: "Chờ phê duyệt",
    sla: "Còn 4h 12m",
    slaPct: 82,
    slaTone: "risk",
    validation: "100% Passed",
    validationTone: "ok",
    flagged: true,
  },
  {
    sar_id: "SAR-2026-009",
    sender: "Võ Thành",
    senderRole: "AML Investigator",
    status: "needs_info",
    statusLabel: "Cần bổ sung",
    sla: "2d 18h còn lại",
    slaPct: 45,
    slaTone: "warn",
    validation: "Thiếu chứng từ ID",
    validationTone: "warn",
    flagged: false,
  },
  {
    sar_id: "SAR-2026-010",
    sender: "Lê Anh",
    senderRole: "Compliance Officer",
    status: "pending",
    statusLabel: "Chờ phê duyệt",
    sla: "1d 04h còn lại",
    slaPct: 60,
    slaTone: "info",
    validation: "100% Passed",
    validationTone: "ok",
    flagged: true,
  },
  {
    sar_id: "SAR-2026-011",
    sender: "Mai Hoa",
    senderRole: "Associate",
    status: "needs_info",
    statusLabel: "Cần bổ sung",
    sla: "3d 22h còn lại",
    slaPct: 25,
    slaTone: "warn",
    validation: "Failed Auto-Check",
    validationTone: "risk",
    flagged: false,
  },
];

/** Chi tiết SAR-2026-010 — khớp screenshot "Chi tiết Phê duyệt SAR". */
export const APPROVAL_DETAIL = {
  sar_id: "SAR-2026-010",
  status: "PENDING_REVIEW" as const,
  suspicionType:
    "Cấu trúc giao dịch (Structuring) - Chia nhỏ số tiền để tránh ngưỡng báo cáo.",
  riskLevel: "CAO",
  subject: {
    name: "Công ty TNHH Global Tech",
    taxCode: "MST: 0312456789",
    internalRating: "HR - HIGH RISK",
    establishedFor: "14 tháng",
    previousSars: "02 lượt",
  },
  behaviourSummary:
    "Khách hàng đã thực hiện chuỗi 15 giao dịch nộp tiền mặt tại các chi nhánh khác nhau trong vòng 48 giờ. Mỗi giao dịch có giá trị từ 180 triệu đến 195 triệu VNĐ, ngay dưới ngưỡng báo cáo bắt buộc 200 triệu VNĐ. Các chi nhánh phân bố rải rác trên địa bàn TP.HCM và Đồng Nai. Tiền sau đó được chuyển lệnh đi quốc tế ngay lập tức với nội dung \"Thanh toán hợp đồng thương mại\" nhưng không đính kèm chứng từ đối ứng hợp lệ.",
  transactions: [
    {
      transaction_id: "TRX-892731",
      time: "20/05/2026 09:12",
      amount: "195,000,000 VNĐ",
      location: "CN Quận 1, TP.HCM",
    },
    {
      transaction_id: "TRX-892735",
      time: "20/05/2026 10:45",
      amount: "188,500,000 VNĐ",
      location: "CN Quận 3, TP.HCM",
    },
    {
      transaction_id: "TRX-892742",
      time: "20/05/2026 14:20",
      amount: "192,000,000 VNĐ",
      location: "CN Biên Hòa, ĐN",
    },
  ],
  networkConfidence: 92,
  networkNote:
    "AI xác định thực thể này có liên kết gián tiếp với 3 cá nhân nằm trong danh sách đen (Blacklist) thông qua các giao dịch chuyển tiền trung gian.",
  history: [
    {
      time: "21/05/2026 08:30",
      text: "Báo cáo hoàn tất Validation",
      actor: "Hệ thống tự động",
    },
    {
      time: "20/05/2026 17:15",
      text: "Đã trình MLRO phê duyệt",
      actor: "Nguyễn Văn An (Analyst)",
    },
  ],
};
