/**
 * Lớp truy cập API của FIN-07 AML Console.
 *
 * Đường dẫn mặc định là `/api/v1` — đường dẫn tương đối, cùng gốc với trang.
 * Ở Docker và trên VM, nginx trong container web proxy `/api/` sang service
 * `api` (xem web/nginx.conf); khi chạy `npm run dev`, Vite proxy sang
 * localhost:8000 (xem web/vite.config.ts). Cả hai đường đều không đi qua
 * CORS, nên không có biến nào phải đặt đúng lúc build.
 *
 * Đặt VITE_API_BASE_URL nếu backend nằm ở gốc khác — khi đó phải mở CORS
 * tương ứng ở CORS_ORIGINS phía backend.
 */

import type { Evidence, NetworkEdge, NetworkNode, SarDraft, User } from "../types";

const BASE = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "") + "/api/v1";
export const SESSION_TOKEN_KEY = "fin07.session.token";
export const AUTH_EXPIRED_EVENT = "fin07:auth-expired";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  const token = window.sessionStorage.getItem(SESSION_TOKEN_KEY);
  try {
    response = await fetch(`${BASE}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...init?.headers,
      },
    });
  } catch (cause) {
    // fetch chỉ ném khi không nối được tới máy chủ. Phân biệt với lỗi HTTP
    // bên dưới là có ích: một bên là backend chưa lên, bên kia là backend
    // trả lời nhưng từ chối.
    throw new ApiError(0, "Không kết nối được tới máy chủ API");
  }

  if (!response.ok) {
    // FastAPI trả lỗi ở trường `detail`. Giữ nguyên câu chữ đó — backend đã
    // giải thích bằng tiếng Việt vì sao thao tác bị từ chối.
    let detail = `Máy chủ trả về ${response.status}`;
    try {
      const body = await response.json();
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      /* thân phản hồi không phải JSON — giữ thông báo mặc định */
    }
    if (response.status === 401 && path !== "/auth/login") {
      window.dispatchEvent(new CustomEvent(AUTH_EXPIRED_EVENT, { detail }));
    }
    throw new ApiError(response.status, detail);
  }

  return (await response.json()) as T;
}

// ---------------------------------------------------------------------
// Kiểu dữ liệu — khớp src/models/schemas.py.
// Số thập phân của PostgreSQL đi qua JSON dưới dạng chuỗi ("92.36"), nên
// khai báo là string và ép kiểu ở chỗ hiển thị bằng num().
// ---------------------------------------------------------------------

export interface ApiCustomer {
  customer_id: string;
  account_key: string;
  customer_type: "individual" | "organisation";
  prototype: "salaried" | "household_business" | "enterprise" | "shell_entity";
  occupation: string;
  declared_income_band: string;
  expected_monthly_volume: string;
  registered_country: string;
  risk_rating: "low" | "medium" | "high";
  onboarding_date: string;
  account_status: string;
  bank_code: string;
}

export interface ApiAlert {
  alert_id: string;
  account_key: string;
  customer_id: string;
  occupation: string;
  risk_rating: "low" | "medium" | "high";
  typology_code: string;
  typology_label: string;
  detector: "rule" | "ml" | "graph";
  risk_score: string;
  status: "open" | "grouped" | "closed";
  case_id: string | null;
  created_at: string;
  factor_count: number;
}

export interface ApiAlertPage {
  rows: ApiAlert[];
  total: number;
  page: number;
  pageSize: number;
}

export interface ApiAlertReason {
  factor_code: string;
  factor_label: string;
  contribution: string;
  weight: string;
  detector: "rule" | "ml" | "graph";
  typology_code: string;
}

export interface ApiTransaction {
  transaction_id: number;
  occurred_at: string;
  from_account_key: string;
  to_account_key: string;
  amount: string;
  currency: string;
  channel: string;
  direction: "in" | "out";
}

export interface ApiAlertDetail extends ApiAlert {
  customer: ApiCustomer;
  reasons: ApiAlertReason[];
  transactions: ApiTransaction[];
  case_state: string | null;
}

export interface ApiCase {
  case_id: string;
  subject_account_key: string;
  title: string;
  state: string;
  risk_score: string;
  priority: "low" | "medium" | "high" | "critical";
  assigned_to: string | null;
  created_at: string;
  alert_count: number;
}

export interface ApiTimelineStep {
  state: string;
  label: string;
  status: "done" | "active" | "pending";
  occurred_at: string | null;
}

export interface ApiCaseDetail extends ApiCase {
  evidence_count: number;
  reasons: ApiAlertReason[];
  customer: ApiCustomer | null;
  timeline: ApiTimelineStep[];
  alert_ids: string[];
}

export interface ApiAuditEvent {
  audit_id: number;
  case_id: string | null;
  event_type: string;
  actor: string;
  actor_role: string;
  payload: Record<string, unknown>;
  occurred_at: string;
}

export interface ApiTypologyShare {
  typology_code: string;
  typology_label: string;
  alert_count: number;
  share_pct: number;
}

export interface ApiDashboard {
  open_alerts: number;
  high_risk_alerts: number;
  cases_investigating: number;
  sar_pending: number;
  avg_risk_score: number;
  latest_batch_id: string | null;
  latest_source_name: string | null;
  transactions_analyzed: number;
  subjects_analyzed: number;
  subjects_below_threshold: number;
  subjects_triggered: number;
  batch_alerts_created: number;
  typology_distribution: ApiTypologyShare[];
  top_alerts: ApiAlert[];
  queue_depth: number;
  worker_alive: boolean;
}

export interface ApiInvestigate {
  job_id: string;
  case_id: string;
  status: string;
  state_before: string;
}

export interface ApiReady {
  status: string;
  database: boolean;
  redis: boolean;
}

export interface ApiLogin {
  token: string;
  user: User;
}

export interface ApiSar extends SarDraft {
  subject: {
    customerId: string;
    accountKey: string;
    customerType: string;
    occupation: string;
    riskRating: string;
    onboardingDate: string;
  };
  evidence: Evidence[];
  approval: null | {
    approval_id: string;
    decision: "pending" | "approved" | "rejected" | "more_info";
    decided_by: string | null;
    reason: string | null;
    requested_at: string;
    decided_at: string | null;
  };
}

export interface ApiNetwork {
  case_id: string;
  risk_score: string;
  subject_account_key: string;
  nodes: NetworkNode[];
  edges: NetworkEdge[];
  transactions: Array<Record<string, string | number>>;
}

export interface ApiSetting {
  code: string;
  label: string;
  value: string;
  unit: string;
  source: string;
  updated_at: string;
}

// ---------------------------------------------------------------------
// Kiểu dữ liệu của các màn hình "Thành phố tài chính".
// Khớp src/models/fc_schemas.py. Ở đây số đã là number: fc_routes.py ép kiểu
// Decimal trước khi trả về, khác với các endpoint cũ trả chuỗi.
// ---------------------------------------------------------------------

export interface FcNavCounts {
  alerts: number;
  approvals: number;
  critical: number;
  /** Kỳ dữ liệu đang hiển thị, dạng ISO `YYYY-MM-DD`. */
  data_period_start: string | null;
  data_period_end: string | null;
}

export interface FcSearchHit {
  id: string;
  label: string;
  kind: string;
  href: string;
}

export interface FcHub {
  id: string;
  name: string;
  country: string;
  lat: number;
  lon: number;
  // "unknown" cho dữ liệu vận hành: quốc gia suy được từ tên ngân hàng, còn
  // mức rủi ro pháp vực là quyết định chính sách nên chưa gán.
  jurisdiction_risk: "low" | "medium" | "high" | "unknown";
  inbound: number;
  outbound: number;
  volume_usd: number;
  alerts: number;
  entities: number;
  risk_score: number;
}

export interface FcFlow {
  id: string;
  source_hub: string;
  target_hub: string;
  source_name: string;
  target_name: string;
  slat: number;
  slon: number;
  tlat: number;
  tlon: number;
  channel: "bank" | "p2p" | "vasp" | "chain" | "gamb" | "proj";
  currency: string;
  amount_native: number;
  volume_usd: number;
  txn_count: number;
  risk_score: number;
  typology_hint: string | null;
  alert_count: number;
  first_seen: string;
  last_seen: string;
}

export interface FcWorld {
  hubs: FcHub[];
  flows: FcFlow[];
  simulation_id: string | null;
  scenario_package: string | null;
  data_mode: "operational";
  source_id: string | null;
  source_name: string | null;
  transaction_count: number;
  geography_available: boolean;
  limitation: string | null;
}


/** Một chặng trong mẫu hình do bộ dò đồ thị tìm được. */
export interface PatternHop {
  seq: number;
  source: string;
  target: string;
  transaction_id: string;
  occurred_at: string | null;
  amount: number | null;
  currency: string | null;
  gap_hours: number | null;
}

/** Mẫu hình đã dò được, dựng thành trình tự có số tiền và thời điểm.
 *
 * Khác với chu trình dò trên vùng đang vẽ: vùng ấy là lân cận một chặng quanh
 * tài khoản có cảnh báo — 48 đỉnh với 47 cạnh, tức một cây — nên về mặt toán học
 * không thể có chu trình. Đây là kết quả bộ dò đã chạy trên toàn đồ thị.
 */
export interface DetectedPattern {
  evidence_id: string;
  pattern: string;
  account_key: string;
  accounts: string[];
  hop_count: number;
  duration_hours: number | null;
  detector_version: string;
  as_of_time: string;
  hops: PatternHop[];
}

export interface FcGraphNode {
  id: string;
  type: string;
  label: string;
  sub: string;
  risk: number;
  first: string;
  last: string;
  hub: string | null;
  negative: boolean;
}

export interface FcGraphEdge {
  id: string;
  s: string;
  t: string;
  kind: string;
  label: string;
  amt: number | null;
  inferred: boolean;
  conf: number | null;
  logic: string | null;
  known_from: string;
  /**
   * Chứng cứ giao dịch, tổng hợp từ bảng `transaction` thật.
   *
   * `tx_count === 0` là câu trả lời hợp lệ và hay gặp: quan hệ sở hữu, dùng
   * chung thiết bị hay chuyển on-chain không có chuyển khoản ngân hàng nào
   * đứng sau. Giao diện phải nói thẳng điều đó, không được suy ra một con số.
   */
  tx_count: number;
  /** Không cộng nhiều loại tiền vào một số — khoá là mã ISO. */
  amounts_by_currency: Record<string, number>;
  tx_first_seen: string | null;
  tx_last_seen: string | null;
}

export interface FcGraph {
  nodes: FcGraphNode[];
  edges: FcGraphEdge[];
}

export interface FcCryptoTransfer {
  id: string;
  chain: string;
  tx_hash: string;
  from_address: string;
  to_address: string;
  asset: string;
  amount: number;
  amount_usd: number | null;
  block_time: string;
  kind: string;
  link_confidence: number | null;
}

export interface FcExposure {
  address: string;
  service_id: string;
  service_type: string;
  exposure_kind: "direct" | "indirect";
  hops: number;
  confidence: number;
  source_id: string;
  known_from: string;
}

export interface FcCrypto {
  transfers: FcCryptoTransfer[];
  exposures: FcExposure[];
  total_usd: number;
  source_mode: "on_chain" | "ledger";
}

export interface FcProject {
  id: string;
  name: string;
  symbol: string;
  chain: string;
  contract_address: string;
  deployer_address: string;
  launched_at: string;
  holder_gini: number | null;
  liquidity_usd: number;
  liquidity_removed_pct: number | null;
  privileged_functions: string[];
  kol_channels: number;
  domain_age_days: number | null;
  risk_score: number;
  status: string;
}

export interface FcAgentStep {
  id: string;
  index: number;
  tool: string;
  input_summary: string;
  output_summary: string;
  /** Khớp ràng buộc CHECK của `investigation_tool_call`, viết thường. */
  status: "succeeded" | "failed" | "timeout" | "partial";
  started_at: string;
  duration_ms: number;
  evidence_refs: string[];
}

export interface FcAgentRun {
  id: string;
  case_id: string | null;
  alert_id: string | null;
  /** Tên tác tử trong `investigation_agent_run` — ba tác tử chạy nối tiếp. */
  tier: "investigation_supervisor" | "explanation_agent" | "evidence_critic";
  started_at: string;
  finished_at: string | null;
  status: "running" | "succeeded" | "failed" | "timeout";
  model_version: string;
  conclusion: string;
  confidence: number | null;
  token_cost: number;
  step_count: number;
}

export interface FcAgentRunDetail extends FcAgentRun {
  steps: FcAgentStep[];
}

export interface FcBenchmark {
  id: string;
  task_id: string;
  scenario_package: string;
  model_version: string;
  split: string;
  metric_name: string;
  metric_value: number;
  target_value: number | null;
  evaluated_at: string;
  passed: boolean | null;
}

export interface FcModelMonitor {
  model_version: string;
  observed_at: string;
  metric_name: string;
  metric_value: number;
  drift_score: number | null;
  status: "healthy" | "watch" | "degraded";
}

export interface FcDataQuality {
  id: string;
  dataset: string;
  check_name: string;
  dimension: string;
  observed_at: string;
  pass_rate: number;
  threshold: number;
  rows_checked: number;
  rows_failed: number;
  status: "pass" | "warn" | "fail";
  detail: string;
}

export interface FcObservation {
  id: string;
  evidence_item_id: string;
  observer_role: "BANK" | "FIU" | "REGULATOR" | "LAW_ENFORCEMENT" | "PUBLIC";
  available_from: string;
  acquisition_type: string;
  legal_basis_id: string | null;
  redaction_profile: string;
  source_confidence: number;
  chain_of_custody_id: string | null;
  is_visible_to_model: boolean;
  summary: string;
}

export interface FcSource {
  source_id: string;
  source_type: string;
  scope: string;
  period: string;
  jurisdiction: string;
  confidence: number;
  access_level: string;
  prohibited_uses: string;
}

export interface FcTxRow {
  id: number;
  source_id: string | null;
  occurred_at: string;
  from_account: string;
  to_account: string;
  amount: number;
  currency: string;
  amount_received: number | null;
  receiving_currency: string | null;
  channel: string;
  remarks: string;
  model_score: number | null;
  threshold: number | null;
  triggered: boolean | null;
  model_version: string | null;
  is_laundering: boolean | null;
}

export interface FcTxPage {
  rows: FcTxRow[];
  total: number;
  page: number;
  pageSize: number;
}

export interface EdgeModelRelease {
  release_id: string;
  model_version: string;
  dataset: string;
  split: string;
  model_sha256: string;
  scores_sha256: string;
  source_database_sha256: string;
  threshold: number;
  transaction_rows: number;
  positive_rows: number;
  triggered_rows: number;
  feature_count: number;
  benchmark: {
    primary_seed: Record<string, number>;
    over_seeds: { count: number; f1_mean: number; f1_sample_std: number };
    operating_points: Array<Record<string, number>>;
  };
  policy: Record<string, boolean | string>;
  status: string;
  trained_at: string;
  activated_at: string | null;
}

export type InvestigationStatus =
  | "QUEUED"
  | "INVESTIGATING"
  | "COMPLETED"
  | "INSUFFICIENT_EVIDENCE"
  | "NEEDS_HUMAN_REVIEW"
  | "FAILED";

export interface ApiRiskComponent {
  score: number;
  weight: number;
  contribution: number;
  available: boolean;
  source_ref: string | null;
}

export interface ApiRiskBreakdown {
  alert_id: string;
  final_risk_score: number;
  score_scale: "0-1";
  fusion_available: boolean;
  components: Record<string, ApiRiskComponent>;
  source_of_truth: "detection_engine";
  limitation: string | null;
}

export interface ApiValidationIssue {
  type: string;
  claim: string;
  evidence_ref: string | null;
  required_tool: string | null;
  detail: string;
}

export interface ApiValidation {
  status: "PASS" | "FAIL";
  confidence: number;
  issues: ApiValidationIssue[];
  missing_evidence: string[];
  unsupported_claims: string[];
  next_action: "RETURN_TO_INVESTIGATION" | "BUILD_CASE_PACKAGE";
}

export interface ApiInvestigationState {
  investigation_id: string;
  alert_id: string;
  case_id: string;
  account_key: string;
  status: InvestigationStatus;
  workflow_state: string;
  iteration: number;
  tool_call_count: number;
  snapshot_time: string;
  risk_summary: Partial<ApiRiskBreakdown>;
  accounts_expanded: string[];
  open_questions: string[];
  validation: ApiValidation | null;
  failure_reason: string | null;
  human_review: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
}

export interface ApiInvestigationStart {
  investigation_id: string;
  alert_id: string;
  case_id: string;
  job_id: string;
  status: "QUEUED";
}

export interface ApiInvestigationEvidence {
  evidence_id: string;
  type: string;
  source: string;
  account_key: string;
  payload: Record<string, unknown>;
  transaction_refs: string[];
  created_at: string;
  integrity: {
    source_system: string;
    source_record_ids: string[];
    content_hash: string;
  };
  is_untrusted_content: boolean;
}

export interface ApiClaim {
  claim_id: string;
  claim: string;
  claim_type: "FACT" | "INFERENCE";
  evidence_refs: string[];
  confidence: number;
}

export interface ApiExplanation {
  summary: string;
  risk_drivers: Array<{
    source: "rule" | "anomaly" | "graph";
    score: number;
    weight: number;
    contribution: number;
    reason: string;
    evidence_refs: string[];
  }>;
  claims: ApiClaim[];
  facts: string[];
  inferences: string[];
  missing_information: string[];
  typologies: string[];
  confidence: number;
  recommended_action: string;
  requires_human_review: true;
}

export interface ApiTraceEvent {
  trace_id: string;
  investigation_id: string;
  agent: string;
  event_type: string;
  tool: string | null;
  input_summary: Record<string, unknown>;
  output_ref: string | null;
  short_rationale: string;
  occurred_at: string;
}

// ---------------------------------------------------------------------
// Điểm gọi
// ---------------------------------------------------------------------

function query(params: Record<string, string | number | boolean | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") search.set(key, String(value));
  }
  const qs = search.toString();
  return qs ? `?${qs}` : "";
}

export const api = {
  loginUsers: () => request<User[]>("/auth/users"),

  login: (email: string, password: string) =>
    request<ApiLogin>("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }),

  me: () => request<User>("/auth/me"),

  logout: () => request<{ ok: boolean }>("/auth/logout", { method: "POST" }),

  dashboard: () => request<ApiDashboard>("/dashboard"),

  alerts: (
    params: {
      status?: string;
      typology_code?: string;
      min_risk?: number;
      limit?: number;
    } = {},
  ) =>
    request<ApiAlert[]>(`/alerts${query(params)}`),

  alertsPage: (
    params: {
      status?: string;
      typology_code?: string;
      min_risk?: number;
      q?: string;
      page?: number;
      page_size?: number;
    } = {},
  ) => request<ApiAlertPage>(`/alerts/page${query(params)}`),

  alert: (alertId: string) => request<ApiAlertDetail>(`/alerts/${encodeURIComponent(alertId)}`),

  latestInvestigation: (alertId: string) =>
    request<ApiInvestigationState | null>(`/alerts/${encodeURIComponent(alertId)}/investigation`),

  investigateAlert: (alertId: string) =>
    request<ApiInvestigationStart>(`/alerts/${encodeURIComponent(alertId)}/investigate`, { method: "POST" }),

  investigation: (investigationId: string) =>
    request<ApiInvestigationState>(`/investigations/${encodeURIComponent(investigationId)}`),

  investigationEvidence: (investigationId: string) =>
    request<ApiInvestigationEvidence[]>(`/investigations/${encodeURIComponent(investigationId)}/evidence`),

  investigationTrace: (investigationId: string) =>
    request<ApiTraceEvent[]>(`/investigations/${encodeURIComponent(investigationId)}/trace`),

  investigationExplanation: (investigationId: string) =>
    request<ApiExplanation>(`/investigations/${encodeURIComponent(investigationId)}/explanation`),

  reviewInvestigation: (investigationId: string, decision: string, reason: string) =>
    request<ApiInvestigationState>(`/investigations/${encodeURIComponent(investigationId)}/review`, {
      method: "POST",
      body: JSON.stringify({ decision, reason }),
    }),

  cases: (params: { state?: string; limit?: number } = {}) => request<ApiCase[]>(`/cases${query(params)}`),

  case: (caseId: string) => request<ApiCaseDetail>(`/cases/${encodeURIComponent(caseId)}`),

  investigate: (caseId: string) =>
    request<ApiInvestigate>(`/cases/${encodeURIComponent(caseId)}/investigate`, { method: "POST" }),

  network: (caseId: string) => request<ApiNetwork>(`/cases/${encodeURIComponent(caseId)}/network`),

  createSar: (caseId: string) =>
    request<ApiSar>(`/cases/${encodeURIComponent(caseId)}/sar`, { method: "POST" }),

  sars: () => request<ApiSar[]>("/sars"),

  sar: (sarId: string) => request<ApiSar>(`/sars/${encodeURIComponent(sarId)}`),

  validateSar: (sarId: string) =>
    request<ApiSar>(`/sars/${encodeURIComponent(sarId)}/validate`, { method: "POST" }),

  submitSar: (sarId: string, reason: string) =>
    request<ApiSar>(`/sars/${encodeURIComponent(sarId)}/submit`, {
      method: "POST",
      body: JSON.stringify({ reason }),
    }),

  decideApproval: (approvalId: string, decision: "approved" | "rejected" | "more_info", reason: string) =>
    request<ApiSar>(`/approvals/${encodeURIComponent(approvalId)}/decision`, {
      method: "POST",
      body: JSON.stringify({ decision, reason }),
    }),

  exportSar: (sarId: string) =>
    request<{ filename: string; status: string }>(`/sars/${encodeURIComponent(sarId)}/export`, { method: "POST" }),

  users: () => request<User[]>("/users"),

  updateUser: (userId: string, active: boolean, reason: string) =>
    request<User>(`/users/${encodeURIComponent(userId)}`, {
      method: "PATCH",
      body: JSON.stringify({ active, reason }),
    }),

  settings: () => request<{ settings: ApiSetting[]; watchlistVersions: Array<Record<string, string>> }>("/settings"),

  updateSetting: (code: string, value: string, reason: string) =>
    request<ApiSetting>(`/settings/${encodeURIComponent(code)}`, {
      method: "PUT",
      body: JSON.stringify({ value, reason }),
    }),

  audit: (params: { case_id?: string; event_type?: string; limit?: number } = {}) =>
    request<ApiAuditEvent[]>(`/audit${query(params)}`),

  // -------------------------------------------------------------------
  // API phân tích mở rộng. Khi không có simulation, World/Graph/Crypto đọc
  // trực tiếp release vận hành HI-Medium và công bố rõ giới hạn nguồn.
  // -------------------------------------------------------------------

  navCounts: () => request<FcNavCounts>("/nav-counts"),

  search: (q: string) => request<FcSearchHit[]>(`/search${query({ q })}`),

  world: () => request<FcWorld>("/world"),

  entityGraph: (limit = 400) => request<FcGraph>(`/fc/graph${query({ limit })}`),
  graphPatterns: (accounts: string[], pattern?: string, limit = 25) =>
    request<DetectedPattern[]>(`/fc/graph/patterns${query({ accounts: accounts.join(","), pattern, limit })}`),

  crypto: (limit = 200) => request<FcCrypto>(`/fc/crypto${query({ limit })}`),

  projects: () => request<FcProject[]>("/fc/projects"),

  agentRuns: () => request<FcAgentRun[]>("/fc/agent-runs"),

  agentRun: (runId: string) => request<FcAgentRunDetail>(`/fc/agent-runs/${encodeURIComponent(runId)}`),

  benchmarks: () => request<FcBenchmark[]>("/fc/benchmarks"),

  modelMonitor: () => request<FcModelMonitor[]>("/fc/model-monitor"),

  edgeModelRelease: () => request<EdgeModelRelease>("/fc/edge-model/release"),

  dataQuality: () => request<FcDataQuality[]>("/fc/data-quality"),

  observations: () => request<FcObservation[]>("/fc/observations"),

  sources: () => request<FcSource[]>("/fc/sources"),

  transactions: (
    params: {
      q?: string;
      channel?: string;
      min_amount?: number;
      min_score?: number;
      currency?: string;
      triggered?: boolean;
      page?: number;
      page_size?: number;
    } = {},
  ) => request<FcTxPage>(`/transactions${query(params)}`),

  /** Giao dịch thật nằm sau một cạnh quan hệ trong đồ thị. */
  graphEdgeTransactions: (
    edgeId: string,
    params: { page?: number; page_size?: number; min_amount?: number; currency?: string } = {},
  ) => request<FcTxPage>(`/fc/graph/edges/${encodeURIComponent(edgeId)}/transactions${query(params)}`),

  /** Giao dịch của một thực thể; trả rỗng với thực thể không phải tài khoản. */
  graphNodeTransactions: (
    nodeId: string,
    params: { direction?: "all" | "in" | "out"; page?: number; page_size?: number } = {},
  ) => request<FcTxPage>(`/fc/graph/nodes/${encodeURIComponent(nodeId)}/transactions${query(params)}`),

  // Không nằm dưới /api/v1 — đây là endpoint hạ tầng của chính ứng dụng.
  ready: () => {
    const root = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");
    return fetch(`${root}/health/ready`).then((r) => r.json() as Promise<ApiReady>);
  },
};

/** Ép số thập phân dạng chuỗi của PostgreSQL về number để hiển thị. */
export function num(value: string | number | null | undefined): number {
  if (value === null || value === undefined) return 0;
  return typeof value === "number" ? value : Number.parseFloat(value);
}
