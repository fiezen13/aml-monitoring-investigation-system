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

/** "3 phút trước". Dữ liệu lịch sử có thể nằm sau đồng hồ máy — khi
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
  unknown: "Chưa gán",
};

/** Loại khách hàng. Giá trị thô (`organisation`) vẫn dùng để so sánh trong mã. */
export function customerTypeLabel(type: string | null | undefined): string {
  if (type === "organisation") return "Tổ chức";
  if (type === "individual") return "Cá nhân";
  return type || "—";
}

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
  // Không để tên kiến trúc mô hình ("MEGA-PNA") ra hàng đợi: các nguồn khác đều
  // gọi theo CÁCH phát hiện bằng tiếng Việt thường, và từ khi nhánh IBM chuyển
  // sang mô hình đồ thị thì nhãn này xuất hiện trên MỌI cảnh báo IBM. Tên mô hình
  // vẫn còn nguyên ở trang Giám sát mô hình (chỉ Admin xem được).
  mega_pna: "Mạng lưới",
  geo_rule: "Luật địa lý",
};

/** Nhãn bộ dữ liệu, cho hàng đợi phục vụ nhiều nguồn cùng lúc. */
const DATASET_LABELS: Record<string, string> = {
  ibm_hi_medium: "Ngân hàng",
  saml_d: "SAML-D",
};

export function datasetLabel(dataset: string): string {
  return DATASET_LABELS[dataset] ?? dataset;
}

/**
 * Rút gọn tên release/nguồn về thương hiệu bộ dữ liệu.
 *
 * `edge_model_release.dataset` là chuỗi tự do như "IBM AML LI-Small
 * currency-native" — biến thể (LI-Small/HI-Medium) là chi tiết nội bộ, người
 * dùng console chỉ cần biết nguồn là "IBM". Giữ nguyên tên nếu không nhận ra.
 */
export function sourceBrand(name: string | null | undefined): string {
  if (!name) return "";
  const s = name.toLowerCase();
  if (s.includes("ibm")) return "IBM";
  if (s.includes("saml")) return "SAML-D";
  if (s.includes("bitcoin") || s.includes("elliptic")) return "Bitcoin";
  return name;
}

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
  agent_query: "Tác tử truy vấn",
  alert_raised: "Phát sinh cảnh báo",
  case_state_changed: "Chuyển trạng thái",
  submitted_for_approval: "Gửi phê duyệt",
  approved: "Phê duyệt",
  rejected: "Từ chối",
  more_info_requested: "Yêu cầu bổ sung",
  file_exported: "Xuất hồ sơ",
  case_viewed: "Xem hồ sơ",
  user_login: "Đăng nhập",
  setting_changed: "Thay đổi cấu hình",
  user_changed: "Thay đổi người dùng",
  sar_updated: "Cập nhật SAR",
  validation_run: "Kiểm chứng SAR",
  // Sự kiện của phiên điều tra. Thiếu chúng thì màn hình hiện nguyên mã
  // "investigation_completed" cho chuyên viên đọc.
  investigation_started: "Bắt đầu điều tra",
  investigation_completed: "Điều tra xong",
  investigation_failed: "Điều tra dừng giữa chừng",
  investigation_reviewed: "Chuyên viên kết luận điều tra",
  // Vòng đời đề xuất của trợ lý điều phối.
  action_proposed: "Trợ lý đề xuất thao tác",
  action_confirmed: "Quản lý xác nhận thao tác",
  action_executed: "Đã thực hiện thao tác",
  action_cancelled: "Đã huỷ đề xuất",
  action_rejected_by_policy: "Đề xuất bị chính sách từ chối",
  action_expired: "Đề xuất hết hạn",
  // Hàng đợi rà soát tiền mã hoá.
  crypto_review_opened: "Đưa giao dịch vào rà soát",
  crypto_review_assigned: "Giao lượt rà soát",
  crypto_review_concluded: "Kết luận rà soát",
  case_assigned: "Đổi người phụ trách",
};

/** Tác nhân của một dòng lịch sử, viết cho người đọc.
 *
 * `actor` là mã dùng cho vết kiểm toán: mã người dùng ("U-001"), tiến trình
 * ("api", "investigation-worker"), và cả tên tác vụ nội bộ do người vận hành
 * đặt khi chạy lại hàng loạt. Không mã nào trong số đó có nghĩa với chuyên viên.
 */
const SYSTEM_ACTORS: Record<string, string> = {
  api: "Hệ thống",
  system: "Hệ thống",
  "investigation-worker": "Trợ lý điều tra",
};

export function actorLabel(actor: string | null | undefined, name?: string | null): string {
  if (name) return name;
  const key = String(actor ?? "").trim();
  if (!key) return "Hệ thống";
  return SYSTEM_ACTORS[key] ?? "Hệ thống";
}

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
  LapLuanGanTypology: "Lập luận gán nhóm hành vi",
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

/**
 * Nhãn BƯỚC điều tra bằng ngôn ngữ nghiệp vụ — dùng cho dòng thời gian ở Chi
 * tiết vụ việc. Khác `caseStateLabel` (badge trạng thái, khớp domain.py): bản
 * này mô tả VIỆC mà chuyên viên hiểu, không phản ánh tên hàm/triển khai. Ví dụ
 * "Tính toán bằng công cụ" → "Phân tích định lượng chỉ số"; "Soạn hồ sơ nghi
 * vấn" tách khỏi SAR/STR (SAR/STR chỉ ở bước Xuất hồ sơ, sau phê duyệt).
 */
const CASE_STEP_LABELS: Record<string, string> = {
  TiepNhanCanhBao: "Tiếp nhận cảnh báo",
  TruyHoiBangChung: "Thu thập bằng chứng",
  PhanTichDoThi: "Phân tích mạng lưới giao dịch",
  DoiChieuTrungPhatPEP: "Đối chiếu danh sách trừng phạt / PEP",
  TinhToanBangCongCu: "Phân tích định lượng chỉ số",
  LapLuanGanTypology: "Đối chiếu nhóm hành vi",
  SoanHoSoNghiVan: "Soạn tóm tắt điều tra",
  KiemChungBangChung: "Kiểm chứng bằng chứng",
  ChoNguoiPheDuyet: "Chờ người phê duyệt",
  DieuTraBoSung: "Điều tra bổ sung",
  XuatHoSo: "Lập báo cáo SAR/STR",
  DongKhongBaoCao: "Đóng, không báo cáo",
};

export function caseStepLabel(state: string): string {
  return CASE_STEP_LABELS[state] ?? state;
}

/**
 * Tiêu đề vụ việc hướng nghiệp vụ. `aml_case.title` sinh tự động thường là
 * "Explainable investigation for ALERT-..." — tên kỹ thuật, không giúp phân
 * biệt vụ theo chủ thể. Gặp mẫu đó thì thay bằng nhãn theo tài khoản chủ thể.
 */
export function caseDisplayTitle(title: string, subjectAccountKey: string): string {
  const technical = /explainable investigation|investigation for|^case for|alert-/i.test(title ?? "");
  if (!title || technical) return `Hồ sơ chủ thể ${subjectAccountKey}`;
  return title;
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

const INVESTIGATION_STATUS_LABELS: Record<string, string> = {
  QUEUED: "Đang chờ",
  INVESTIGATING: "Đang điều tra",
  COMPLETED: "Hoàn tất",
  FAILED: "Thất bại",
  INSUFFICIENT_EVIDENCE: "Chưa đủ bằng chứng",
  NEEDS_HUMAN_REVIEW: "Cần chuyên viên rà soát",
};

export function investigationStatusLabel(status: string): string {
  return INVESTIGATION_STATUS_LABELS[status] ?? status;
}

const VALIDATION_STATUS_LABELS: Record<string, string> = {
  PASS: "Đạt",
  FAIL: "Không đạt",
  PENDING: "Đang chờ",
};

export function validationStatusLabel(status: string): string {
  return VALIDATION_STATUS_LABELS[status] ?? status;
}

const TRACE_EVENT_LABELS: Record<string, string> = {
  INVESTIGATION_STARTED: "Bắt đầu điều tra",
  EVIDENCE_ADDED: "Bổ sung bằng chứng",
  AGENT_DECISION: "Tác tử đưa ra quyết định",
  TOOL_CALL: "Gọi công cụ",
  TOOL_RESULT: "Nhận kết quả công cụ",
  EXPLANATION_GENERATED: "Tạo bản giải thích",
  VALIDATION_PASS: "Kiểm chứng đạt",
  VALIDATION_FAIL: "Kiểm chứng không đạt",
  CRITIC_OBJECTION_REFUTED: "Bác bỏ khiếu nại của tác tử phản biện",
  INVESTIGATION_COMPLETED: "Hoàn tất điều tra",
  HUMAN_REVIEW_REQUIRED: "Yêu cầu chuyên viên rà soát",
  GEMINI_REQUEST: "Gửi yêu cầu tới Gemini",
  GEMINI_RESPONSE: "Nhận phản hồi từ Gemini",
  GEMINI_ERROR: "Lỗi Gemini",
  INVALID_TOOL_REQUEST: "Yêu cầu công cụ không hợp lệ",
  INVESTIGATION_FAILED: "Điều tra thất bại",
};

export function traceEventLabel(eventType: string): string {
  return TRACE_EVENT_LABELS[eventType] ?? eventType.replaceAll("_", " ");
}

const AGENT_LABELS: Record<string, string> = {
  investigation_supervisor: "Tác tử điều phối điều tra",
  explanation_agent: "Tác tử giải thích rủi ro",
  evidence_critic: "Tác tử phản biện bằng chứng",
  system: "Hệ thống",
  human_analyst: "Chuyên viên phân tích",
  orchestrator: "Bộ điều phối quy trình",
};

export function agentLabel(agent: string): string {
  return AGENT_LABELS[agent] ?? agent;
}

const TOOL_LABELS: Record<string, string> = {
  GetRiskBreakdown: "Lấy chi tiết điểm rủi ro",
  GetTransactions: "Lấy giao dịch",
  GetAccountBehavior: "Lấy đặc trưng hành vi tài khoản",
  GetAnomalyExplanation: "Lấy giải thích điểm bất thường",
  GetGraphEvidence: "Lấy bằng chứng đồ thị",
  GetGraphNeighborhood: "Lấy vùng lân cận trên đồ thị",
  GetTypology: "Tra cứu nhóm hành vi",
  get_alert_risk_summary: "Lấy tóm tắt rủi ro cảnh báo",
  get_alert_transactions: "Lấy giao dịch của cảnh báo",
  get_customer_profile: "Lấy hồ sơ khách hàng",
  get_behavior_features: "Lấy đặc trưng hành vi",
  get_feature_attribution: "Lấy mức đóng góp của đặc trưng",
  get_graph_pattern: "Lấy mẫu hình đồ thị",
  get_graph_neighbors: "Lấy các đỉnh lân cận",
  get_typology_definition: "Tra cứu định nghĩa nhóm hành vi",
  get_case_notes: "Lấy ghi chú vụ việc",
  fetch_alert_context: "Lấy bối cảnh cảnh báo",
  expand_entity_graph: "Mở rộng đồ thị thực thể",
  device_correlation: "Đối chiếu thiết bị",
  screen_watchlist: "Đối chiếu danh sách theo dõi",
  trace_crypto_exposure: "Truy vết phơi nhiễm tài sản mã hoá",
  request_vasp_records: "Yêu cầu hồ sơ từ VASP",
  draft_str_narrative: "Soạn nội dung báo cáo STR",
  request_human_review: "Yêu cầu chuyên viên rà soát",
};

export function toolLabel(tool: string): string {
  return TOOL_LABELS[tool] ?? tool;
}

const RISK_COMPONENT_LABELS: Record<string, string> = {
  behavior: "Hành vi",
  anomaly: "Bất thường",
  graph: "Đồ thị",
  rules: "Luật nghiệp vụ",
  rule: "Luật nghiệp vụ",
  mega_pna: "Mô hình phân tích mạng lưới giao dịch",
  geo_rule: "Bộ luật địa lý",
};

export function riskComponentLabel(component: string): string {
  return RISK_COMPONENT_LABELS[component] ?? component;
}

const EVIDENCE_TYPE_LABELS: Record<string, string> = {
  RISK_BREAKDOWN: "Cơ sở tính điểm rủi ro",
  BEHAVIOR_FEATURE: "Dấu hiệu hành vi tài khoản",
  ANOMALY_EXPLANATION: "Lý do được xem là bất thường",
  TRANSACTION: "Giao dịch liên quan",
  TYPOLOGY_MAPPING: "Nhóm hành vi được đối chiếu",
  GRAPH_PATTERN: "Mô hình luân chuyển tiền",
  GRAPH_NEIGHBORHOOD: "Quan hệ giao dịch liên quan",
  RULE_TRIGGER: "Quy tắc cảnh báo đã kích hoạt",
};

export function evidenceTypeLabel(type: string): string {
  return EVIDENCE_TYPE_LABELS[type] ?? type;
}

/** Tên nguồn dành cho chuyên viên. Tên bảng và tên dịch vụ vẫn được giữ ở API
 * để truy vết, nhưng không nên bắt người dùng tự dịch chúng khi đọc hồ sơ. */
const EVIDENCE_SOURCE_LABELS: Record<string, string> = {
  detection_engine: "Hệ thống phát hiện cảnh báo",
  rule_engine: "Bộ quy tắc cảnh báo",
  feature_service: "Hệ thống phân tích hành vi",
  transaction_service: "Kho dữ liệu giao dịch",
  typology_registry: "Danh mục nhóm hành vi",
  anomaly_explanation_service: "Hệ thống phân tích bất thường",
  graph_detector: "Hệ thống phân tích quan hệ giao dịch",
  transaction: "Kho dữ liệu giao dịch",
  alert: "Hệ thống cảnh báo",
  behavior_feature_snapshot: "Kho dữ liệu hành vi",
};

export function evidenceSourceLabel(source: string | null | undefined): string {
  if (!source) return "Hệ thống nghiệp vụ";
  const known = EVIDENCE_SOURCE_LABELS[source];
  if (known) return known;
  // Nguồn của bằng chứng "quy tắc đã kích hoạt" được SINH RA từ tên bộ phát
  // hiện (`mega_pna` → `mega_pna_engine`), nên bảng tra cứng sẽ thủng ngay lần
  // thêm bộ phát hiện tiếp theo. Bắt theo hậu tố để bộ mới cũng có tên đọc được.
  const engine = source.match(/^(.+)_engine$/);
  if (engine) return `Bộ phát hiện ${detectorLabel(engine[1]).toLowerCase()}`;
  return "Hệ thống nghiệp vụ";
}

const EVIDENCE_SOURCE_TITLES: Record<string, string> = {
  detection_engine: "Cơ sở tính điểm rủi ro",
  rule_engine: "Quy tắc cảnh báo đã kích hoạt",
  feature_service: "Dấu hiệu hành vi tài khoản",
  transaction_service: "Giao dịch liên quan",
  typology_registry: "Nhóm hành vi được đối chiếu",
  anomaly_explanation_service: "Lý do được xem là bất thường",
  graph_detector: "Quan hệ giao dịch liên quan",
  transaction: "Giao dịch liên quan",
};

/** "1083674.330000000000000000 Ruble" → "1.083.674,33 Ruble".
 *
 * Cột NUMERIC của PostgreSQL đi qua chuỗi giữ nguyên 18 chữ số thập phân. Đổ
 * thẳng ra bảng thì chuyên viên phải đọc một dãy số vô nghĩa và không so sánh
 * được hai dòng với nhau. */
export function formatAmountText(raw: string | null | undefined): string {
  const text = String(raw ?? "").trim();
  // Cho phép dấu tách hàng nghìn NẰM TRONG phần số: máy chủ nay trả
  // "1 083 674.33 Ruble" (dấu cách mảnh U+202F). Nếu regex dừng ở khoảng trắng
  // đầu tiên thì "083 674.33 Ruble" bị đọc thành tên loại tiền.
  const match = text.match(/^(-?[\d.,\u202f\u00a0 ]+)(.*)$/);
  if (!match) return text || "—";
  const value = Number(match[1].replace(/[\s\u202f\u00a0,]/g, ""));
  if (!Number.isFinite(value)) return text;
  const money = value.toLocaleString("vi-VN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return match[2] ? `${money} ${match[2].trim()}` : money;
}

export function evidenceTitle(type: string | undefined, source: string | undefined): string {
  if (type) return evidenceTypeLabel(type);
  return (source && EVIDENCE_SOURCE_TITLES[source]) || "Bằng chứng nghiệp vụ";
}

type EvidencePayload = Record<string, unknown>;

function windowLabel(value: unknown): string {
  const raw = String(value ?? "");
  const match = raw.match(/^(\d+)d$/);
  return match ? `${match[1]} ngày` : raw;
}

/** Một câu tóm tắt ngắn cho danh sách bằng chứng. Phần dữ liệu đầy đủ vẫn nằm
 * trong ngăn chi tiết; danh sách chỉ trả lời nhanh "bằng chứng này nói gì?". */
export function evidenceSummary(type: string | undefined, payload: unknown): string {
  const p = (payload ?? {}) as EvidencePayload;

  switch (type) {
    case "RISK_BREAKDOWN": {
      const score = typeof p.final_risk_score === "number" ? `${(p.final_risk_score * 100).toFixed(1)}%` : null;
      return score ? `Điểm rủi ro được hệ thống xác định là ${score}.` : "Chi tiết các yếu tố tạo nên điểm rủi ro.";
    }
    case "RULE_TRIGGER": {
      const rules = Array.isArray(p.triggered_rules)
        ? (p.triggered_rules as EvidencePayload[]).filter(
            (rule) => !String(rule.factor_code ?? "").startsWith("CTX_"),
          )
        : [];
      if (rules.length === 1) {
        const label = String(rules[0].factor_label ?? "").trim();
        return label ? `Quy tắc đã kích hoạt: ${label}.` : "Có 1 quy tắc cảnh báo đã kích hoạt.";
      }
      return rules.length > 1
        ? `Có ${rules.length} quy tắc cảnh báo đã kích hoạt.`
        : "Mở để xem quy tắc và điều kiện đã kích hoạt cảnh báo.";
    }
    case "BEHAVIOR_FEATURE": {
      const window = windowLabel(p.window);
      return window
        ? `Số liệu hành vi của tài khoản trong ${window}.`
        : "Các dấu hiệu hành vi được hệ thống tổng hợp từ giao dịch.";
    }
    case "ANOMALY_EXPLANATION": {
      const score = typeof p.anomaly_score === "number" ? p.anomaly_score.toFixed(2) : null;
      return score
        ? `Mức độ bất thường ${score}, kèm các dấu hiệu ảnh hưởng nhiều nhất.`
        : "Các dấu hiệu khiến hoạt động này khác với thông lệ.";
    }
    case "TRANSACTION": {
      const count = Array.isArray(p.items) ? p.items.length : 0;
      return count > 0
        ? `${count} giao dịch được dùng để đối chiếu nhận định.`
        : "Danh sách giao dịch được dùng để đối chiếu nhận định.";
    }
    case "TYPOLOGY_MAPPING": {
      const code = String(p.typology_code ?? "").trim();
      const name = String(p.name_vi ?? "").trim();
      if (code && name) return `${code} — ${name}.`;
      if (code) return `Nhóm hành vi ${code}.`;
      return "Kết quả đối chiếu với danh mục nhóm hành vi của ngân hàng.";
    }
    case "GRAPH_PATTERN": {
      const accounts = Array.isArray(p.accounts) ? p.accounts.length : 0;
      return accounts > 0
        ? `Mối liên hệ luân chuyển tiền giữa ${accounts} tài khoản.`
        : "Mối liên hệ luân chuyển tiền giữa các tài khoản.";
    }
    case "GRAPH_NEIGHBORHOOD": {
      const nodes = Array.isArray(p.nodes) ? p.nodes.length : 0;
      return nodes > 0
        ? `${nodes} tài khoản nằm trong phạm vi giao dịch liên quan.`
        : "Các tài khoản và giao dịch có liên quan trực tiếp.";
    }
    default:
      return "Mở để xem nội dung và nguồn dữ liệu của bằng chứng.";
  }
}

const VALIDATION_ISSUE_LABELS: Record<string, string> = {
  UNSUPPORTED_CLAIM: "Nhận định chưa có bằng chứng",
  CONTRADICTION: "Mâu thuẫn",
  MISSING_EVIDENCE: "Thiếu bằng chứng",
  INVALID_SCORE: "Điểm không hợp lệ",
  INVALID_TYPOLOGY: "Nhóm hành vi không hợp lệ",
  INVALID_SCORE_CONTRIBUTION: "Ghi sai mức đóng góp của nhánh",
  MISSING_SOURCE_RECORD: "Thiếu bản ghi nguồn",
  PROHIBITED_CONCLUSION: "Kết luận không được phép",
  OTHER: "Vấn đề khác",
};

export function validationIssueLabel(type: string): string {
  return VALIDATION_ISSUE_LABELS[type] ?? type;
}

const RECOMMENDED_ACTION_LABELS: Record<string, string> = {
  CONTINUE_MONITORING: "Tiếp tục giám sát",
  REQUEST_MORE_INFORMATION: "Yêu cầu bổ sung thông tin",
  ESCALATE_TO_L2: "Chuyển lên cấp rà soát 2",
  REVIEW_FOR_SAR_STR: "Rà soát để lập báo cáo SAR/STR",
  CLOSE_AS_LIKELY_FALSE_POSITIVE: "Đóng do nhiều khả năng là cảnh báo giả",
};

export function recommendedActionLabel(action: string): string {
  return RECOMMENDED_ACTION_LABELS[action] ?? action;
}

const ROLE_LABELS: Record<string, string> = {
  // Ba vai trò hiện hành.
  analyst: "Chuyên viên",
  manager: "Quản lý",
  admin: "Quản trị hệ thống",
  // Giá trị actor_role lịch sử trong audit_log (bản ghi cũ vẫn hiển thị đúng).
  mlro: "MLRO",
  compliance_officer: "Chuyên viên tuân thủ",
  auditor: "Kiểm toán viên",
  system: "Hệ thống",
  agent: "Tác tử",
  investigator: "Điều tra viên",
};

export function roleLabel(role: string): string {
  return ROLE_LABELS[role] ?? role;
}

const PROFILE_VALUE_LABELS: Record<string, string> = {
  kyc_unavailable: "Chưa có thông tin KYC",
  active: "Đang hoạt động",
  inactive: "Không hoạt động",
  suspended: "Tạm khoá",
  closed: "Đã đóng",
};

export function profileValueLabel(value: string): string {
  // Nghề nghiệp khi thiếu KYC được ghi kèm TÊN BỘ DỮ LIỆU gốc — "KYC unavailable
  // - IBM AML HI-Medium", "KYC unavailable - SAML-D". Khớp chính xác từng chuỗi
  // là thua: mỗi lần nạp một bộ mới lại lọt một biến thể tiếng Anh ra màn hình
  // nghiệp vụ. Khớp theo tiền tố, và bỏ luôn tên bộ dữ liệu — chuyên viên chỉ
  // cần biết hồ sơ này chưa có KYC, không cần biết nó đến từ kho nào.
  if (/^KYC unavailable/i.test(value)) return "Chưa có thông tin KYC";
  return PROFILE_VALUE_LABELS[value] ?? value;
}

/**
 * Kênh thanh toán, Việt hoá và HỢP NHẤT giữa các bộ dữ liệu.
 *
 * Cùng một khái niệm đang được hai bộ ghi hai kiểu — IBM ghi `CREDIT_CARD`,
 * SAML-D ghi `Credit card` — nên màn hình tra cứu hiện lẫn lộn cả hai, và cả
 * hai đều là mã thô. Chuẩn hoá về một nhãn tiếng Việt cho mỗi khái niệm.
 */
const PAYMENT_CHANNEL_LABELS: Record<string, string> = {
  cheque: "Séc",
  ach: "Chuyển khoản ACH",
  creditcard: "Thẻ tín dụng",
  debitcard: "Thẻ ghi nợ",
  crossborder: "Chuyển tiền quốc tế",
  cash: "Tiền mặt",
  cashwithdrawal: "Rút tiền mặt",
  cashdeposit: "Nộp tiền mặt",
  wire: "Điện chuyển tiền",
  bitcoin: "Bitcoin",
};

/**
 * Số tiền theo cách viết Việt Nam, KHÔNG kèm đơn vị.
 *
 * Nơi gọi phải tự in loại tiền ngay cạnh — chính vì hàm cũ tự dán sẵn "₫" mà
 * màn hình soạn SAR hiện tổng Đô la Canada dưới nhãn đồng Việt Nam.
 */
export function formatMoney(amount: number): string {
  return amount.toLocaleString("vi-VN", { maximumFractionDigits: 2 });
}

/**
 * Trạng thái của một dòng phân công.
 *
 * Máy chủ trả MÃ nghiệp vụ; câu chữ nằm ở đây. Người dùng không bao giờ nhìn
 * thấy `in_progress` hay `due_soon`.
 */
const ASSIGNMENT_STATUS_LABELS: Record<string, string> = {
  unassigned: "Chưa phân công",
  in_progress: "Đang xử lý",
  needs_info: "Chờ bổ sung",
  due_soon: "Sắp đến hạn",
  overdue: "Quá hạn",
  completed: "Hoàn thành",
};

export function assignmentStatusLabel(status: string): string {
  return ASSIGNMENT_STATUS_LABELS[status] ?? status;
}

/** Đường mà một lượt phân công đi tới, không phải người chịu trách nhiệm. */
export function assignmentSourceLabel(source: string | null | undefined): string {
  if (source === "ai_copilot") return "Trợ lý AI";
  if (source === "manual") return "Thủ công";
  return "—";
}

/**
 * Cách nói KÈM TÊN NGƯỜI: "qua Trợ lý AI" chứ không phải "Trợ lý AI".
 *
 * Cột chỉ ghi "Trợ lý AI" đọc ra thành "AI đã giao hồ sơ này" — sai về trách
 * nhiệm nghiệp vụ. Trợ lý chỉ soạn đề xuất; người bấm xác nhận mới là người
 * giao, và tên họ phải đứng trước. Ô này chỉ nói việc ấy tới bằng đường nào.
 */
export function assignmentChannelLabel(source: string | null | undefined): string {
  if (source === "ai_copilot") return "qua Trợ lý AI";
  if (source === "manual") return "giao trực tiếp";
  return "";
}

/**
 * Việc này tới tay người xử lý bằng cách nào.
 *
 * Chuyên viên bấm "Nhận vụ" thì `assigned_by` chính là họ — không ai giao cả.
 * Gọi đó là "giao trực tiếp" là kể sai: nó ngụ ý có một người thứ hai đã quyết
 * định, trong khi đây là người tự nhận việc về mình. So theo MÃ chứ không theo
 * tên, vì hai người trùng tên là chuyện có thật.
 */
export function assignmentOriginLabel(
  source: string | null | undefined,
  assignedById: string | null | undefined,
  assigneeId: string | null | undefined,
): string {
  if (assignedById && assigneeId && assignedById === assigneeId) return "tự nhận vụ việc";
  return assignmentChannelLabel(source);
}

/**
 * Hạn xử lý, kể bằng lời chứ không chỉ bằng màu.
 *
 * "Còn 5 giờ" đọc được ngay; một chấm vàng thì phải học mới hiểu, và người mù
 * màu thì không hiểu được. Màu là lớp thứ hai, không phải lớp duy nhất.
 */
export function deadlineText(dueAt: string | null | undefined, now: Date = new Date()): string {
  if (!dueAt) return "Chưa đặt hạn";
  const diffMs = new Date(dueAt).getTime() - now.getTime();
  const hours = Math.round(Math.abs(diffMs) / 3_600_000);
  const days = Math.round(Math.abs(diffMs) / 86_400_000);
  if (diffMs < 0) return days >= 1 ? `Quá hạn ${days} ngày` : `Quá hạn ${hours} giờ`;
  if (hours < 1) return "Còn dưới 1 giờ";
  if (hours < 48) return `Còn ${hours} giờ`;
  return `Còn ${days} ngày`;
}

export function paymentChannelLabel(channel: string | null | undefined): string {
  if (!channel) return "—";
  const key = channel.toLowerCase().replace(/[\s_-]/g, "");
  return PAYMENT_CHANNEL_LABELS[key] ?? channel;
}

const COUNTRY_LABELS: Record<string, string> = {
  VN: "Việt Nam",
  KH: "Campuchia",
  SG: "Singapore",
  HK: "Hồng Kông",
  US: "Hoa Kỳ",
  XX: "Chưa xác định",
};

export function countryLabel(country: string): string {
  return COUNTRY_LABELS[country] ?? country;
}

/** Việt hoá tương thích các bản điều tra cũ đã được ghi bất biến bằng tiếng Anh. */
export function investigationTextVi(value: string): string {
  if (!value) return value;

  // Bước "thiếu bằng chứng bắt buộc" nhúng thẳng MÃ bộ phát hiện vào một câu
  // tiếng Việt. Phải xử lý TRƯỚC chỗ tách "; " ngay dưới, vì chính câu này có
  // dấu chấm phẩy và sẽ bị cắt đôi trước khi tới bất kỳ luật dịch nào.
  value = value.replace(
    /cảnh báo loại '([a-z0-9_]+)'/g,
    (_whole, detector: string) => `cảnh báo nhóm ${detectorLabel(detector).toLowerCase()}`,
  );

  if (value.includes("; ")) return value.split("; ").map(investigationTextVi).join("; ");

  // Bản giải thích được ghi BẤT BIẾN tại thời điểm điều tra, nên những bản đã
  // sinh trước khi tác tử biết Việt hoá kênh vẫn mang nguyên "qua kênh
  // CREDIT_CARD". Không chạy lại cả trăm phiên điều tra chỉ vì một cụm từ —
  // đổi ở lớp hiển thị, số liệu và vết kiểm toán giữ nguyên.
  value = value.replace(/qua kênh ([A-Za-z][A-Za-z_-]*(?: [A-Za-z][a-z]+)?)/g, (whole, channel: string) => {
    const vi = paymentChannelLabel(channel);
    return vi === channel ? whole : `qua kênh ${vi.toLowerCase()}`;
  });

  const exact: Record<string, string> = {
    "Obtain the authoritative score and available detector branch first.":
      "Lấy điểm chính thức và nhánh phát hiện hiện có trước.",
    "Anomaly branch requires source feature values before narrative explanation.":
      "Nhánh bất thường cần giá trị đặc trưng nguồn trước khi tạo bản giải thích.",
    "Collect deterministic feature deviation attribution for the Isolation Forest score.":
      "Thu thập mức đóng góp sai lệch đặc trưng được tính tất định cho điểm Isolation Forest.",
    "Collect bounded source transactions supporting the alert context.":
      "Thu thập tập giao dịch nguồn có giới hạn để đối chiếu bối cảnh cảnh báo.",
    "Resolve typology through the versioned catalog rather than prompt knowledge.":
      "Đối chiếu nhóm hành vi qua danh mục có phiên bản, không dựa vào kiến thức của lời nhắc.",
    "Tool completed with status SUCCEEDED.": "Công cụ hoàn tất thành công.",
    "Agent output is advisory and cannot perform a final AML business action.":
      "Đầu ra của tác tử chỉ mang tính tư vấn và không thể tự thực hiện quyết định nghiệp vụ AML cuối cùng.",
    "Critic PASS; validated draft package is ready for an analyst.":
      "Tác tử phản biện xác nhận đạt; gói bản nháp đã kiểm chứng sẵn sàng cho chuyên viên.",
    "Gemini structured output passed SDK and Pydantic validation.":
      "Đầu ra có cấu trúc của Gemini đã vượt qua kiểm chứng SDK và Pydantic.",
    "Submitted versioned system instruction and structured evidence context.":
      "Đã gửi chỉ dẫn hệ thống có phiên bản cùng ngữ cảnh bằng chứng có cấu trúc.",
    "Generated structured FACT/INFERENCE output from cited evidence only.":
      "Đã tạo đầu ra DỮ KIỆN/SUY LUẬN có cấu trúc chỉ từ bằng chứng được trích dẫn.",
    "Every claim and source record passed deterministic verification.":
      "Mọi nhận định và bản ghi nguồn đều vượt qua bước kiểm chứng tất định.",
    "Alert accepted and immutable snapshot time fixed.":
      "Đã tiếp nhận cảnh báo và cố định thời điểm chụp dữ liệu bất biến.",
    "Transaction results were truncated; additional pages may be required.":
      "Kết quả giao dịch đã bị cắt bớt; có thể cần truy vấn thêm các trang tiếp theo.",
    "Anomaly is the authoritative detector branch for this alert.":
      "Bất thường là nhánh phát hiện chính thức của cảnh báo này.",
  };
  if (exact[value]) return exact[value];

  let match = value.match(/^The detection engine assigned final risk score ([\d.]+) to alert (.+)\.$/);
  if (match) return `Bộ máy phát hiện đã gán điểm rủi ro cuối cùng ${match[1]} cho cảnh báo ${match[2]}.`;
  match = value.match(/^Feature (.+) had value (.+) at reference percentile (.+)\.$/);
  if (match) return `Đặc trưng ${match[1]} có giá trị ${match[2]} tại phân vị tham chiếu ${match[3]}.`;
  match = value.match(/^The bounded transaction query returned (\d+) records for review\.$/);
  if (match) return `Truy vấn giao dịch có giới hạn trả về ${match[1]} bản ghi để rà soát.`;
  match = value.match(/^Alert (.+) is high-risk primarily because of the (.+) branch\. The explanation is limited to cited bank-side evidence and requires analyst review\.$/);
  if (match) return `Cảnh báo ${match[1]} có rủi ro cao chủ yếu do nhánh ${match[2] === "anomaly" ? "bất thường" : match[2]}. Bản giải thích chỉ dựa trên bằng chứng phía ngân hàng đã trích dẫn và cần chuyên viên rà soát.`;
  match = value.match(/^The available signals should be compared with (.+) \((.+)\); this is an investigative interpretation, not a finding of money laundering\.$/);
  if (match) {
    const names: Record<string, string> = {
      "Intermediary account network": "Mạng tài khoản trung gian",
      "Structuring below reporting threshold": "Chia nhỏ dưới ngưỡng báo cáo",
    };
    return `Cần đối chiếu các tín hiệu hiện có với ${match[1]} (${names[match[2]] ?? match[2]}); đây là nhận định phục vụ điều tra, không phải kết luận về hành vi rửa tiền.`;
  }
  match = value.match(/^Added (.+) from allow-listed source (.+)\.$/);
  if (match) {
    return `Đã bổ sung bằng chứng ${evidenceTypeLabel(match[1])} từ ${evidenceSourceLabel(match[2])}.`;
  }
  return value;
}
