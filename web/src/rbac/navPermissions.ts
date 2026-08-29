/**
 * Ánh xạ đường dẫn nav → quyền cần có, DÙNG CHUNG với route guard trong App.tsx
 * (một nguồn sự thật). Sidebar lọc mục theo đúng quyền route yêu cầu, nên menu và
 * quyền truy cập không bao giờ lệch. Đường dẫn không có trong bảng = mọi người
 * đã đăng nhập đều thấy (vd /dashboard, /world).
 */
import { PERMISSIONS, type Permission } from "./permissions";

export const NAV_PERMISSION: Record<string, Permission> = {
  "/dashboard": PERMISSIONS.VIEW_DASHBOARD,
  "/world": PERMISSIONS.VIEW_DASHBOARD,
  "/alerts": PERMISSIONS.VIEW_ALERTS,
  "/assignments": PERMISSIONS.VIEW_CASES,
  "/cases": PERMISSIONS.VIEW_CASES,
  "/network": PERMISSIONS.VIEW_ENTITY_GRAPH,
  "/transactions": PERMISSIONS.VIEW_TRANSACTIONS,
  "/crypto": PERMISSIONS.VIEW_CRYPTO,
  "/agents": PERMISSIONS.VIEW_MODEL_QUALITY,
  "/benchmarks": PERMISSIONS.VIEW_MODEL_QUALITY,
  "/models": PERMISSIONS.VIEW_MODEL_QUALITY,
  "/data-quality": PERMISSIONS.VIEW_MODEL_QUALITY,
  "/reports": PERMISSIONS.VIEW_REPORTS,
  "/approvals": PERMISSIONS.APPROVE_CASE,
  "/audit": PERMISSIONS.VIEW_AUDIT_LOG,
  "/users": PERMISSIONS.MANAGE_USERS,
  "/settings": PERMISSIONS.MANAGE_SYSTEM,
};
