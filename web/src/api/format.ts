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
  mega_pna: "MEGA-PNA",
  geo_rule: "Luật địa lý",
};

/** Nhãn bộ dữ liệu, cho hàng đợi phục vụ nhiều nguồn cùng lúc. */
const DATASET_LABELS: Record<string, string> = {
  ibm_hi_medium: "Ngân hàng",
  saml_d: "Xuyên biên giới",
};

export function datasetLabel(dataset: string): string {
  return DATASET_LABELS[dataset] ?? dataset;
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
  mega_pna: "Mô hình đồ thị MEGA-PNA",
  geo_rule: "Bộ luật địa lý",
};

export function riskComponentLabel(component: string): string {
  return RISK_COMPONENT_LABELS[component] ?? component;
}

const EVIDENCE_TYPE_LABELS: Record<string, string> = {
  RISK_BREAKDOWN: "Chi tiết điểm rủi ro",
  BEHAVIOR_FEATURE: "Đặc trưng hành vi",
  ANOMALY_EXPLANATION: "Giải thích điểm bất thường",
  TRANSACTION: "Giao dịch",
  TYPOLOGY_MAPPING: "Ánh xạ nhóm hành vi",
  GRAPH_PATTERN: "Mẫu hình đồ thị",
  GRAPH_NEIGHBORHOOD: "Vùng lân cận đồ thị",
  RULE_TRIGGER: "Luật đã kích hoạt",
};

export function evidenceTypeLabel(type: string): string {
  return EVIDENCE_TYPE_LABELS[type] ?? type;
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
  admin: "Quản trị viên",
  mlro: "MLRO",
  compliance_officer: "Chuyên viên tuân thủ",
  analyst: "Chuyên viên phân tích",
  auditor: "Kiểm toán viên",
  system: "Hệ thống",
  agent: "Tác tử",
  investigator: "Điều tra viên",
};

export function roleLabel(role: string): string {
  return ROLE_LABELS[role] ?? role;
}

const PROFILE_VALUE_LABELS: Record<string, string> = {
  "KYC unavailable — Behaviour batch import": "Chưa có KYC — nhập từ lô dữ liệu hành vi",
  kyc_unavailable: "Chưa có thông tin KYC",
  active: "Đang hoạt động",
  inactive: "Không hoạt động",
  suspended: "Tạm khoá",
  closed: "Đã đóng",
};

export function profileValueLabel(value: string): string {
  return PROFILE_VALUE_LABELS[value] ?? value;
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
  if (value.includes("; ")) return value.split("; ").map(investigationTextVi).join("; ");

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
    const sources: Record<string, string> = {
      detection_engine: "bộ máy phát hiện",
      feature_service: "dịch vụ đặc trưng",
      transaction_service: "dịch vụ giao dịch",
      typology_registry: "danh mục nhóm hành vi",
      anomaly_explanation_service: "dịch vụ giải thích điểm bất thường",
      graph_detector: "bộ phát hiện đồ thị",
    };
    return `Đã bổ sung bằng chứng ${evidenceTypeLabel(match[1])} từ ${sources[match[2]] ?? match[2]}.`;
  }
  return value;
}
