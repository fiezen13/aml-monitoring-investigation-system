/** Định dạng hiển thị dùng chung cho dữ liệu từ API. */

import { num } from "./client";

const DATE_TIME = new Intl.DateTimeFormat("vi-VN", {
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});

const DATE_ONLY = new Intl.DateTimeFormat("vi-VN", {
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
});

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  return DATE_TIME.format(new Date(iso));
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  return DATE_ONLY.format(new Date(iso));
}

/** "3 phút trước". Dữ liệu seed nằm ở 2026 nên khoảng cách có thể âm — khi
 *  đó hiển thị mốc tuyệt đối thay vì "trong -2 ngày nữa". */
export function formatRelative(iso: string | null | undefined): string {
  if (!iso) return "—";
  const deltaMs = Date.now() - new Date(iso).getTime();
  if (deltaMs < 0) return formatDateTime(iso);

  const minutes = Math.floor(deltaMs / 60000);
  if (minutes < 1) return "vừa xong";
  if (minutes < 60) return `${minutes} phút trước`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} giờ trước`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days} ngày trước`;
  return formatDateTime(iso);
}

export function formatAmount(value: string | number, currency?: string): string {
  const amount = num(value);
  const text = new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 2 }).format(amount);
  return currency ? `${text} ${currency}` : text;
}

export function formatScore(value: string | number): string {
  return num(value).toFixed(1);
}

/** Hai chữ cái đại diện cho chủ thể. Lược đồ không lưu họ tên (dữ liệu tổng
 *  hợp), nên lấy từ mã khách hàng: CUS-00048 → 48. */
export function initials(customerId: string): string {
  const digits = customerId.replace(/\D/g, "");
  return digits.slice(-2) || customerId.slice(0, 2).toUpperCase();
}

const RISK_RATING_LABELS: Record<string, string> = {
  low: "Thấp",
  medium: "Trung bình",
  high: "Cao",
};

export function riskRatingLabel(rating: string): string {
  return RISK_RATING_LABELS[rating] ?? rating;
}

const PROTOTYPE_LABELS: Record<string, string> = {
  salaried: "Người làm công ăn lương",
  household_business: "Hộ kinh doanh",
  enterprise: "Doanh nghiệp",
  shell_entity: "Thực thể vỏ bọc",
};

export function prototypeLabel(prototype: string): string {
  return PROTOTYPE_LABELS[prototype] ?? prototype;
}

const DETECTOR_LABELS: Record<string, string> = {
  rule: "Luật",
  ml: "Học máy",
  graph: "Đồ thị",
};

export function detectorLabel(detector: string): string {
  return DETECTOR_LABELS[detector] ?? detector;
}

const ALERT_STATUS_LABELS: Record<string, string> = {
  open: "Mới",
  grouped: "Đã gom vụ việc",
  closed: "Đã đóng",
};

export function alertStatusLabel(status: string): string {
  return ALERT_STATUS_LABELS[status] ?? status;
}

const AUDIT_EVENT_LABELS: Record<string, string> = {
  agent_query: "Agent truy vấn",
  alert_raised: "Phát sinh cảnh báo",
  case_state_changed: "Chuyển trạng thái",
  submitted_for_approval: "Gửi phê duyệt",
  approved: "Phê duyệt",
  rejected: "Từ chối",
  more_info_requested: "Yêu cầu bổ sung",
  file_exported: "Xuất hồ sơ",
  case_viewed: "Xem hồ sơ",
};

export function auditEventLabel(eventType: string): string {
  return AUDIT_EVENT_LABELS[eventType] ?? eventType;
}

/** Nhãn trạng thái vụ việc — khớp CASE_STATE_LABELS trong src/domain.py. */
const CASE_STATE_LABELS: Record<string, string> = {
  TiepNhanCanhBao: "Tiếp nhận cảnh báo",
  TruyHoiBangChung: "Truy hồi bằng chứng",
  PhanTichDoThi: "Phân tích đồ thị",
  DoiChieuTrungPhatPEP: "Đối chiếu trừng phạt / PEP",
  TinhToanBangCongCu: "Tính toán bằng công cụ",
  LapLuanGanTypology: "Lập luận gán typology",
  SoanHoSoNghiVan: "Soạn hồ sơ nghi vấn",
  KiemChungBangChung: "Kiểm chứng bằng chứng",
  ChoNguoiPheDuyet: "Chờ người phê duyệt",
  DieuTraBoSung: "Điều tra bổ sung",
  XuatHoSo: "Xuất hồ sơ",
  DongKhongBaoCao: "Đóng, không báo cáo",
};

export function caseStateLabel(state: string): string {
  return CASE_STATE_LABELS[state] ?? state;
}

const PRIORITY_LABELS: Record<string, string> = {
  low: "Thấp",
  medium: "Trung bình",
  high: "Cao",
  critical: "Nghiêm trọng",
};

export function priorityLabel(priority: string): string {
  return PRIORITY_LABELS[priority] ?? priority;
}
