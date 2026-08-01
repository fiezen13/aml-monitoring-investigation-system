import type { Evidence } from "../types";

/** Kho bằng chứng — mọi nhận định AI đều phải trỏ về đây (NT1). */
export const EVIDENCE: Evidence[] = [
  {
    id: "EV-00031",
    kind: "statement",
    title: "Phiếu thu tiền gửi #223-X1",
    description:
      "Bằng chứng giao dịch được trích xuất từ hệ thống Core Banking chi nhánh Quận 1. Hiển thị thông tin người nộp tiền là Nguyễn Thành Nam.",
    source: "Core Banking · Backend Analytics",
    fileType: "PDF DOCUMENT",
    fileSize: "2.4 MB",
    createdAt: "12/05/2026 09:41",
    tags: ["Sao kê TK"],
  },
  {
    id: "EV-00045",
    kind: "ownership",
    title: "Sơ đồ quan hệ sở hữu CTY TNHH Blue Ocean",
    description:
      "Kết quả truy vấn đăng ký doanh nghiệp: Nguyễn Thành Nam nắm 35% vốn gián tiếp qua một pháp nhân trung gian. Sinh bởi Network Analysis Tool.",
    source: "Network Analysis Tool · GRAPH-008",
    fileType: "JSON GRAPH",
    fileSize: "182 KB",
    createdAt: "12/05/2026 10:02",
    tags: ["Quan hệ sở hữu"],
  },
  {
    id: "EV-00052",
    kind: "calculation",
    title: "Bảng tính tổng hợp giao dịch dưới ngưỡng",
    description:
      "Kết quả của công cụ tính toán CALC-014: 14 giao dịch trong 95 phút, 82% có giá trị sát dưới ngưỡng báo cáo, tổng 1.372.000.000 VNĐ. Đây là kết quả công cụ mã, không phải số do mô hình sinh (NT2).",
    source: "Công cụ tính toán · CALC-014",
    fileType: "CSV TABLE",
    fileSize: "96 KB",
    createdAt: "12/05/2026 10:15",
    tags: ["Tính toán", "CALC-014"],
  },
  {
    id: "EV-00032",
    kind: "ownership",
    title: "Quan hệ sở hữu",
    description:
      "Liên kết sở hữu giữa chủ thể và hai pháp nhân trung gian, trích từ Network Analysis Tool.",
    source: "Network Analysis Tool",
    fileType: "JSON GRAPH",
    fileSize: "140 KB",
    createdAt: "12/05/2026 10:04",
    tags: ["Quan hệ sở hữu"],
  },
  {
    id: "EV-00033",
    kind: "geo",
    title: "Tọa độ IP",
    description:
      "Lịch sử địa chỉ IP thực hiện lệnh, đối chiếu vị trí đăng nhập với chi nhánh giao dịch.",
    source: "Screening Service · NET-LOG-992",
    fileType: "LOG FILE",
    fileSize: "58 KB",
    createdAt: "12/05/2026 10:20",
    tags: ["IP Clash", "Network"],
  },
  {
    id: "EV-00034",
    kind: "opensource",
    title: "Tin tức OpenSource",
    description:
      "Bài báo công khai liên quan tới đối tác thương mại của chủ thể, thu thập bởi Screening Service.",
    source: "Screening Service · SCREEN-021",
    fileType: "HTML SNAPSHOT",
    fileSize: "1.1 MB",
    createdAt: "12/05/2026 10:26",
    tags: ["OpenSource"],
  },
  {
    id: "EV-00029",
    kind: "id_document",
    title: "Căn cước công dân (Mặt trước)",
    description: "Bản scan giấy tờ định danh trong hồ sơ KYC của khách hàng.",
    source: "KYC Repository",
    fileType: "IMAGE",
    fileSize: "1.2 MB",
    createdAt: "11/05/2026 16:40",
    tags: ["KYC", "ID Card"],
  },
  {
    id: "EV-00030",
    kind: "statement",
    title: "Sao kê tài khoản VCB-1029",
    description: "Sao kê 90 ngày của tài khoản liên quan, trích từ Core Banking.",
    source: "Core Banking · Backend Analytics",
    fileType: "PDF DOCUMENT",
    fileSize: "4.5 MB",
    createdAt: "11/05/2026 17:05",
    tags: ["Sao kê TK"],
  },
];

export function getEvidence(id: string): Evidence | undefined {
  return EVIDENCE.find((e) => e.id === id);
}
