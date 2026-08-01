import { Navigate, Outlet, useLocation } from "react-router-dom";

import { useApp } from "../../context/AppContext";
import { ToastRegion } from "../common/Toast";
import { Header } from "./Header";
import { Sidebar } from "./Sidebar";

const TITLES: [string, string][] = [
  ["/dashboard", "FIN-07 AML"],
  ["/alerts/", "Chi tiết Cảnh báo"],
  ["/alerts", "Hàng đợi Cảnh báo"],
  ["/cases", "Vụ việc"],
  ["/network", "Phân tích Mạng lưới Giao dịch"],
  ["/sar", "Rà soát bản nháp SAR"],
  ["/approvals", "Phê duyệt SAR"],
  ["/audit", "Audit trail"],
  ["/users", "Người dùng & Vai trò"],
  ["/settings", "Cấu hình hệ thống"],
];

/**
 * Application shell: sidebar cố định trái + header sticky + main cuộn được.
 * Trang /login và /403 không dùng shell này.
 */
export function AppLayout() {
  const { currentUser } = useApp();
  const location = useLocation();

  if (!currentUser) {
    return <Navigate to="/login" replace />;
  }

  const title = TITLES.find(([prefix]) => location.pathname.startsWith(prefix))?.[1];

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <Header title={title} />
        <main className="min-h-0 flex-1 overflow-y-auto p-4">
          <Outlet />
        </main>
      </div>
      <ToastRegion />
    </div>
  );
}
