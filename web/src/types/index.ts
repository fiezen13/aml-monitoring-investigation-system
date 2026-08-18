/**
 * Kiểu dữ liệu dùng chung của FIN-07 AML Console.
 *
 * Tên trường bám theo hợp đồng backend hiện có:
 *  - `CaseOut` / `CaseDetailOut` / `AlertReasonOut` trong src/models/schemas.py
 *  - máy trạng thái 12 trạng thái trong db/init/001_schema.sql (Hình 4, ARC-001)
 *  - typology T01–T10 (FIN-07-BUS-001)
 */

export type Role =
  | "compliance_officer"
  | "mlro"
  | "auditor"
  | "admin"
  | "analyst";

export interface User {
  id: string;
  name: string;
  email: string;
  role: Role;
  roleLabel: string;
  active: boolean;
  lastLogin: string | null;
}

/** Trạng thái vụ việc — đúng danh sách CHECK trong db/init/001_schema.sql. */
export type CaseState =
  | "TiepNhanCanhBao"
  | "TruyHoiBangChung"
  | "PhanTichDoThi"
  | "DoiChieuTrungPhatPEP"
  | "TinhToanBangCongCu"
  | "LapLuanGanTypology"
  | "SoanHoSoNghiVan"
  | "KiemChungBangChung"
  | "ChoNguoiPheDuyet"
  | "DieuTraBoSung"
  | "XuatHoSo"
  | "DongKhongBaoCao";

export type Priority = "low" | "medium" | "high" | "critical";

export type AlertStatus = "open" | "in_progress" | "urgent" | "resolved";

/** Một yếu tố đóng góp vào điểm rủi ro — khớp AlertReasonOut (NT7). */
export interface RiskFactor {
  factor_code: string;
  factor_label: string;
  contribution: number;
  weight: number;
  detector: "rule" | "ml" | "graph";
  typology_code: string;
}

export interface CustomerProfile {
  customerId: string;
  name: string;
  initials: string;
  accountKey: string;
  nationality: string;
  segment: string;
  businessLine: string;
  profileAge: string;
  pepLevel: number | null;
  kycValid: boolean;
}

export interface Alert {
  alert_id: string;
  customer: CustomerProfile;
  risk_score: number;
  ai_confidence: number;
  typology_code: string;
  typology_label: string;
  status: AlertStatus;
  statusLabel: string;
  sla: string;
  slaOverdue: boolean;
  created_at: string;
  detector: "rule" | "ml" | "graph";
  summary: string;
  factors: RiskFactor[];
  evidenceIds: string[];
  transactionIds: string[];
  case_id: string | null;
}

export interface Transaction {
  transaction_id: string;
  channel: string;
  amount: number;
  currency: string;
  riskLevel: "high" | "medium" | "low";
  riskLabel: string;
  date: string;
  behaviour: string;
  direction: "in" | "out";
}

export type EvidenceKind =
  | "statement"
  | "ownership"
  | "geo"
  | "opensource"
  | "id_document"
  | "calculation"
  | "screening"
  | "graph"
  | "network_log";

export interface Evidence {
  id: string;
  kind: EvidenceKind;
  title: string;
  description: string;
  source: string;
  fileType: string;
  fileSize: string;
  createdAt: string;
  tags: string[];
}

export interface CaseTimelineStep {
  id: string;
  label: string;
  timestamp: string | null;
  status: "done" | "active" | "pending";
  note: string | null;
}

export interface FlowAnalysisRow {
  date: string;
  transaction_id: string;
  behaviour: string;
  behaviourTone: "risk" | "warn" | "ok" | "info";
}

export type SarStatus =
  | "DRAFT"
  | "VALIDATING"
  | "VALIDATION_FAILED"
  | "VALIDATION_PASSED"
  | "PENDING_REVIEW"
  | "NEEDS_INFO"
  | "APPROVED"
  | "REJECTED";

export interface SarValidationIssue {
  id: string;
  severity: "error" | "warning";
  title: string;
  detail: string;
}

export interface SarStatement {
  id: string;
  text: string;
  evidenceIds: string[];
  highlight?: string;
}

export interface SarDraft {
  sar_id: string;
  case_id: string;
  alert_id: string;
  status: SarStatus;
  suspicionType: string;
  riskLevel: "CAO" | "TRUNG BÌNH" | "THẤP";
  subjectName: string;
  submittedBy: string;
  submittedByRole: string;
  statements: SarStatement[];
  behaviourSummary: string;
  inflow: number;
  outflow: number;
  inflowNote: string;
  outflowNote: string;
  validationIssues: SarValidationIssue[];
  relatedTransactions: SarTransactionRow[];
  networkConfidence: number;
  history: { time: string; text: string; actor: string }[];
}

export interface SarTransactionRow {
  transaction_id: string;
  time: string;
  amount: string;
  location: string;
}

export interface Approval {
  sar_id: string;
  sender: string;
  senderRole: string;
  status: "pending" | "needs_info" | "approved" | "rejected";
  statusLabel: string;
  sla: string;
  slaPct: number;
  slaTone: "risk" | "warn" | "info" | "ok";
  validation: string;
  validationTone: "ok" | "warn" | "risk";
  flagged: boolean;
}

export interface NetworkNode {
  id: string;
  label: string;
  sublabel: string;
  kind: "subject" | "mule" | "company" | "wallet" | "bank";
  risk: "low" | "medium" | "high" | "primary" | "neutral";
}

export interface NetworkEdge {
  id: string;
  source: string;
  target: string;
  label: string;
  suspicious: boolean;
}
