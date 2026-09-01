/**
 * Mã quyền — PHẢN CHIẾU src/api/permissions.py (backend là nguồn sự thật).
 *
 * Giao diện KHÔNG tự suy quyền từ vai trò: danh sách quyền của người dùng đến từ
 * `/auth/me` (`user.permissions`). Hằng số dưới đây chỉ để gọi tên quyền an toàn
 * kiểu (tránh gõ sai chuỗi), không phải để quyết định phân quyền phía client.
 */
export const PERMISSIONS = {
  VIEW_DASHBOARD: "view_dashboard",
  VIEW_EXECUTIVE_DASHBOARD: "view_executive_dashboard",
  VIEW_SYSTEM_DASHBOARD: "view_system_dashboard",
  VIEW_AUDIT_DASHBOARD: "view_audit_dashboard",
  VIEW_ALERTS: "view_alerts",
  INVESTIGATE_ALERT: "investigate_alert",
  VIEW_CASES: "view_cases",
  INVESTIGATE_CASE: "investigate_case",
  ESCALATE_CASE: "escalate_case",
  APPROVE_CASE: "approve_case",
  PREPARE_SAR: "prepare_sar",
  DECIDE_SAR: "decide_sar",
  VIEW_TRANSACTIONS: "view_transactions",
  VIEW_ENTITY_GRAPH: "view_entity_graph",
  VIEW_CRYPTO: "view_crypto",
  VIEW_INVESTIGATION: "view_investigation",
  REVIEW_INVESTIGATION: "review_investigation",
  VIEW_MODEL_EXPLAIN: "view_model_explain",
  VIEW_MODEL_QUALITY: "view_model_quality",
  VIEW_MODEL_GOVERNANCE: "view_model_governance",
  VIEW_REPORTS: "view_reports",
  EXPORT_REPORT: "export_report",
  // Điều phối công việc — phản chiếu nhóm quyền mới ở src/api/permissions.py.
  SAR_READ: "sar.read",
  SAR_ASSIGN: "sar.assign",
  SAR_REASSIGN: "sar.reassign",
  TASK_PRIORITY_UPDATE: "task.priority.update",
  TASK_DEADLINE_UPDATE: "task.deadline.update",
  TASK_REMIND: "task.remind",
  TEAM_WORKLOAD_READ: "team.workload.read",
  VIEW_AUDIT_LOG: "view_audit_log",
  MANAGE_USERS: "manage_users",
  MANAGE_ROLES: "manage_roles",
  MANAGE_SYSTEM: "manage_system",
} as const;

export type Permission = (typeof PERMISSIONS)[keyof typeof PERMISSIONS];
