/**
 * Chọn dashboard theo vai trò tại một URL /dashboard duy nhất.
 *
 * Chủ ý (theo yêu cầu): CHỈ Admin khác — Admin giám sát hệ thống nên có dashboard
 * riêng. Mọi vai trò nghiệp vụ còn lại (chuyên viên phân tích, chuyên viên tuân
 * thủ, MLRO, kiểm toán viên) dùng CHUNG dashboard vận hành đầy đủ biểu đồ như cũ
 * — không tách năm bản tối giản làm mất chart.
 */
import { useRbac } from "../../rbac/useRbac";
import { PERMISSIONS } from "../../rbac/permissions";
import { DashboardPage } from "../DashboardPage";
import { AdminDashboard } from "./AdminDashboard";

export function DashboardRouter() {
  const rbac = useRbac();
  if (rbac.can(PERMISSIONS.VIEW_SYSTEM_DASHBOARD)) return <AdminDashboard />;
  return <DashboardPage />;
}
