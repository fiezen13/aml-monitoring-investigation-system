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
// Điểm gọi
// ---------------------------------------------------------------------

function query(params: Record<string, string | number | undefined>): string {
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

  alerts: (params: { status?: string; typology_code?: string; min_risk?: number; limit?: number } = {}) =>
    request<ApiAlert[]>(`/alerts${query(params)}`),

  alert: (alertId: string) => request<ApiAlertDetail>(`/alerts/${encodeURIComponent(alertId)}`),

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
