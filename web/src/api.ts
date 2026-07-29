export interface AlertReason {
  factor_code: string;
  factor_label: string;
  contribution: string;
  weight: string;
  detector: string;
  typology_code: string;
}

export interface Case {
  case_id: string;
  subject_account_key: string;
  title: string;
  state: string;
  risk_score: string;
  priority: string;
  assigned_to: string | null;
  created_at: string;
  alert_count: number;
}

export interface CaseDetail extends Case {
  evidence_count: number;
  reasons: AlertReason[];
}

export interface QueueStats {
  depth: number;
  worker_alive: boolean;
}

const BASE = "/api/v1";

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${BASE}${path}`);
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText} khi gọi ${path}`);
  }
  return (await response.json()) as T;
}

export const listCases = () => getJson<Case[]>("/cases");
export const getCase = (caseId: string) => getJson<CaseDetail>(`/cases/${caseId}`);
export const getQueueStats = () => getJson<QueueStats>("/queue");

export async function investigate(caseId: string): Promise<{ job_id: string }> {
  const response = await fetch(`${BASE}/cases/${caseId}/investigate`, { method: "POST" });
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return (await response.json()) as { job_id: string };
}
