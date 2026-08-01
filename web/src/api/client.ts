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

const BASE = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "") + "/api/v1";

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
  try {
    response = await fetch(`${BASE}${path}`, {
      headers: { "Content-Type": "application/json" },
      ...init,
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
  dashboard: () => request<ApiDashboard>("/dashboard"),

  alerts: (params: { status?: string; typology_code?: string; min_risk?: number; limit?: number } = {}) =>
    request<ApiAlert[]>(`/alerts${query(params)}`),

  alert: (alertId: string) => request<ApiAlertDetail>(`/alerts/${encodeURIComponent(alertId)}`),

  cases: (params: { state?: string; limit?: number } = {}) => request<ApiCase[]>(`/cases${query(params)}`),

  case: (caseId: string) => request<ApiCaseDetail>(`/cases/${encodeURIComponent(caseId)}`),

  investigate: (caseId: string) =>
    request<ApiInvestigate>(`/cases/${encodeURIComponent(caseId)}/investigate`, { method: "POST" }),

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
