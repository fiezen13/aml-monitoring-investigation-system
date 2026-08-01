import type { AmlCase, NetworkEdge, NetworkNode } from "../types";
import { ALERTS } from "./mockAlerts";

/**
 * Vụ việc — state đúng máy trạng thái Hình 4 (db/init/001_schema.sql).
 * CASE-2026-014 là vụ việc trung tâm, sinh từ ALT-2026-001.
 */
export const CASES: AmlCase[] = [
  {
    case_id: "CASE-2026-014",
    subject_account_key: "ACC-884201",
    title: "Nghi vấn cấu trúc giao dịch",
    state: "PhanTichDoThi",
    risk_score: 89,
    priority: "critical",
    assigned_to: "Nguyễn Quang Hưng",
    created_at: "12/05/2026 09:15",
    alert_count: 1,
    evidence_count: 31,
    customer: ALERTS[0].customer,
    alertId: "ALT-2026-001",
    sarId: "SAR-2026-007",
    timeline: [
      {
        id: "step-1",
        label: "Tiếp nhận hồ sơ",
        timestamp: "12/05/2026 09:15",
        status: "done",
        note: null,
      },
      {
        id: "step-2",
        label: "Truy hồi bằng chứng",
        timestamp: "12/05/2026 10:30",
        status: "done",
        note: "31 file đã gắn",
      },
      {
        id: "step-3",
        label: "Phân tích chuyên sâu",
        timestamp: null,
        status: "active",
        note: "Đang xử lý (85%)",
      },
      {
        id: "step-4",
        label: "Gợi ý Typology",
        timestamp: null,
        status: "pending",
        note: "Chờ xử lý",
      },
      {
        id: "step-5",
        label: "Soạn thảo SAR",
        timestamp: null,
        status: "pending",
        note: "Chưa bắt đầu",
      },
    ],
    flowRows: [
      {
        date: "12/05/2026 09:41",
        transaction_id: "TRX-0091223",
        behaviour: "Dưới ngưỡng (Structuring)",
        behaviourTone: "risk",
      },
      {
        date: "11/05/2026 15:45",
        transaction_id: "TRX-0091219",
        behaviour: "Dưới ngưỡng (Structuring)",
        behaviourTone: "risk",
      },
      {
        date: "11/05/2026 10:20",
        transaction_id: "TRX-0091215",
        behaviour: "Giao dịch nhanh",
        behaviourTone: "warn",
      },
      {
        date: "10/05/2026 14:10",
        transaction_id: "TRX-0091208",
        behaviour: "Chuyển tiền nội bộ",
        behaviourTone: "info",
      },
    ],
  },
  {
    case_id: "CASE-2026-013",
    subject_account_key: "ACC-905522",
    title: "Trùng khớp danh sách trừng phạt",
    state: "DoiChieuTrungPhatPEP",
    risk_score: 94,
    priority: "critical",
    assigned_to: "Trần Hoàng Quân",
    created_at: "11/05/2026 14:02",
    alert_count: 1,
    evidence_count: 12,
    customer: ALERTS[2].customer,
    alertId: "ALT-2026-003",
    sarId: null,
    timeline: [],
    flowRows: [],
  },
  {
    case_id: "CASE-2026-012",
    subject_account_key: "ACC-663017",
    title: "Rà soát hồ sơ PEP cấp 1",
    state: "TruyHoiBangChung",
    risk_score: 81,
    priority: "high",
    assigned_to: "Lê Anh Tuấn",
    created_at: "10/05/2026 08:47",
    alert_count: 2,
    evidence_count: 8,
    customer: ALERTS[4].customer,
    alertId: "ALT-2026-005",
    sarId: null,
    timeline: [],
    flowRows: [],
  },
  {
    case_id: "CASE-2026-011",
    subject_account_key: "ACC-771034",
    title: "Tần suất giao dịch bất thường",
    state: "ChoNguoiPheDuyet",
    risk_score: 64,
    priority: "medium",
    assigned_to: "Nguyễn Quang Hưng",
    created_at: "08/05/2026 11:20",
    alert_count: 1,
    evidence_count: 9,
    customer: ALERTS[1].customer,
    alertId: "ALT-2026-002",
    sarId: "SAR-2026-010",
    timeline: [],
    flowRows: [],
  },
  {
    case_id: "CASE-2026-010",
    subject_account_key: "ACC-118804",
    title: "Giao dịch vùng địa lý rủi ro",
    state: "DongKhongBaoCao",
    risk_score: 32,
    priority: "low",
    assigned_to: "Trần Hoàng Quân",
    created_at: "05/05/2026 16:33",
    alert_count: 1,
    evidence_count: 4,
    customer: ALERTS[3].customer,
    alertId: "ALT-2026-004",
    sarId: null,
    timeline: [],
    flowRows: [],
  },
];

export const CASE_STATE_LABEL: Record<string, string> = {
  TiepNhanCanhBao: "Tiếp nhận cảnh báo",
  TruyHoiBangChung: "Truy hồi bằng chứng",
  PhanTichDoThi: "Đang điều tra",
  DoiChieuTrungPhatPEP: "Đối chiếu trừng phạt/PEP",
  TinhToanBangCongCu: "Tính toán bằng công cụ",
  LapLuanGanTypology: "Lập luận gán typology",
  SoanHoSoNghiVan: "Soạn hồ sơ nghi vấn",
  KiemChungBangChung: "Kiểm chứng bằng chứng",
  ChoNguoiPheDuyet: "Chờ người phê duyệt",
  DieuTraBoSung: "Điều tra bổ sung",
  XuatHoSo: "Đã xuất hồ sơ",
  DongKhongBaoCao: "Đóng không báo cáo",
};

export function getCase(id: string): AmlCase | undefined {
  return CASES.find((c) => c.case_id === id);
}

/** Đồ thị GRAPH-008 — mạng lưới giao dịch của CASE-2026-014. */
export const NETWORK_NODES: NetworkNode[] = [
  {
    id: "n-subject",
    label: "Nguyễn Thành Nam",
    sublabel: "THỰC THỂ CHÍNH",
    kind: "subject",
    risk: "primary",
  },
  {
    id: "n-company",
    label: "CTY TNHH Blue Ocean",
    sublabel: "Thực thể trung gian",
    kind: "company",
    risk: "high",
  },
  {
    id: "n-mule",
    label: "Lê Văn Tám (Mule)",
    sublabel: "Tài khoản thu gom",
    kind: "mule",
    risk: "high",
  },
  {
    id: "n-wallet",
    label: "Ví Điện Tử X-Pay",
    sublabel: "Kênh trung chuyển",
    kind: "wallet",
    risk: "high",
  },
];

export const NETWORK_EDGES: NetworkEdge[] = [
  {
    id: "e1",
    source: "n-mule",
    target: "n-company",
    label: "420M VND",
    suspicious: true,
  },
  {
    id: "e2",
    source: "n-company",
    target: "n-subject",
    label: "440M VND",
    suspicious: true,
  },
  {
    id: "e3",
    source: "n-mule",
    target: "n-wallet",
    label: "440M VND",
    suspicious: true,
  },
  {
    id: "e4",
    source: "n-wallet",
    target: "n-subject",
    label: "500M VND",
    suspicious: true,
  },
];
