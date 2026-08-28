import { Suspense, lazy } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import { AccessDenied } from "./components/common/AccessDenied";
import { ToastRegion } from "./components/common/Toast";
import { AppLayout } from "./components/layout/AppLayout";
import { AppProvider } from "./context/AppContext";
import { ConsoleProvider } from "./context/ConsoleContext";
import { AgentRunPage, AgentsPage } from "./pages/AgentsPage";
import { AlertDetailPage } from "./pages/AlertDetailPage";
import { ApprovalDetailPage } from "./pages/ApprovalDetailPage";
import { ApprovalsPage } from "./pages/ApprovalsPage";
import { AuditPage } from "./pages/AuditPage";
import { BenchmarksPage } from "./pages/BenchmarksPage";
import { CaseDetailPage } from "./pages/CaseDetailPage";
import { CasesPage } from "./pages/CasesPage";
import { DashboardRouter } from "./pages/dashboard/DashboardRouter";
import { RequirePermission } from "./rbac/guards";
import { PERMISSIONS as PERM } from "./rbac/permissions";
import { DataQualityPage } from "./pages/DataQualityPage";
import { LoginPage } from "./pages/LoginPage";
import { ModelsPage } from "./pages/ModelsPage";
import { NotFoundPage } from "./pages/NotFoundPage";
import { ProjectsPage } from "./pages/ProjectsPage";
import { SarEditPage } from "./pages/SarEditPage";
import { SettingsPage } from "./pages/SettingsPage";
import { TransactionsPage } from "./pages/TransactionsPage";
import { UsersPage } from "./pages/UsersPage";
import { LoadingState } from "./components/ui";

/**
 * Ba màn hình nặng nhất được tách khỏi bundle khởi động.
 *
 * Cesium, Three, MapLibre và Cytoscape cộng lại lớn hơn toàn bộ phần còn lại
 * của ứng dụng. Nạp chúng ngay khi mở trang đăng nhập nghĩa là mọi chuyên viên
 * chờ tải cả bộ máy dựng hình 3D chỉ để nhìn một bảng cảnh báo — mà phần lớn
 * phiên làm việc không hề mở tới bản đồ hay đồ thị.
 */
const WorldPage = lazy(() => import("./pages/WorldPage").then((m) => ({ default: m.WorldPage })));
const NetworkPage = lazy(() => import("./pages/NetworkPage").then((m) => ({ default: m.NetworkPage })));
const CryptoPage = lazy(() => import("./pages/CryptoPage").then((m) => ({ default: m.CryptoPage })));

/** Khung chờ đúng tông cho các route tách riêng — không phải màn trắng. */
function HeavyRoute({ children, label }: { children: React.ReactNode; label: string }) {
  return (
    <Suspense
      fallback={
        <div className="grid h-full place-items-center">
          <LoadingState label={label} />
        </div>
      }
    >
      {children}
    </Suspense>
  );
}

export default function App() {
  return (
    <AppProvider>
      <ConsoleProvider>
        <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
          <Routes>
            <Route
              path="/login"
              element={
                <>
                  <LoginPage />
                  <ToastRegion />
                </>
              }
            />
            <Route
              path="/403"
              element={
                <>
                  <AccessDenied />
                  <ToastRegion />
                </>
              }
            />
            <Route element={<AppLayout />}>
              {/* Giám sát */}
              <Route path="/dashboard" element={<DashboardRouter />} />
              <Route
                path="/world"
                element={
                  <HeavyRoute label="Đang nạp bộ dựng bản đồ…">
                    <RequirePermission permission={PERM.VIEW_DASHBOARD}><WorldPage /></RequirePermission>
                  </HeavyRoute>
                }
              />

              {/* Điều tra — gộp về một trang Vụ việc.
                  `/alerts` (hàng đợi) đã gộp KPI phễu vào trang Vụ việc → chuyển
                  hướng. `/alerts/:id` giữ làm fallback cho cảnh báo mồ côi (chưa
                  gom vào vụ). `/network` (toàn mạng) bỏ khỏi điều hướng: đồ thị
                  giờ nằm trong từng vụ; chỉ giữ `/network/:caseId` (toàn màn hình
                  của một vụ), mở từ nút trong trang vụ. */}
              <Route path="/alerts" element={<Navigate to="/cases" replace />} />
              <Route path="/alerts/:alertId" element={<RequirePermission permission={PERM.VIEW_ALERTS}><AlertDetailPage /></RequirePermission>} />
              <Route path="/cases" element={<RequirePermission permission={PERM.VIEW_CASES}><CasesPage /></RequirePermission>} />
              <Route path="/cases/:caseId" element={<RequirePermission permission={PERM.VIEW_CASES}><CaseDetailPage /></RequirePermission>} />
              <Route path="/network" element={<Navigate to="/cases" replace />} />
              <Route
                path="/network/:caseId"
                element={
                  <HeavyRoute label="Đang nạp bộ dựng đồ thị…">
                    <RequirePermission permission={PERM.VIEW_ENTITY_GRAPH}><NetworkPage /></RequirePermission>
                  </HeavyRoute>
                }
              />
              <Route path="/transactions" element={<RequirePermission permission={PERM.VIEW_TRANSACTIONS}><TransactionsPage /></RequirePermission>} />

              {/* Tài sản mã hoá */}
              <Route
                path="/crypto"
                element={
                  <HeavyRoute label="Đang nạp màn truy vết…">
                    <RequirePermission permission={PERM.VIEW_CRYPTO}><CryptoPage /></RequirePermission>
                  </HeavyRoute>
                }
              />
              {/* AI Agent */}
              <Route path="/agents" element={<RequirePermission permission={PERM.VIEW_MODEL_QUALITY}><AgentsPage /></RequirePermission>} />
              <Route path="/agents/:runId" element={<RequirePermission permission={PERM.VIEW_MODEL_QUALITY}><AgentRunPage /></RequirePermission>} />

              {/* Chất lượng và mô hình */}
              <Route path="/benchmarks" element={<RequirePermission permission={PERM.VIEW_MODEL_QUALITY}><BenchmarksPage /></RequirePermission>} />
              <Route path="/models" element={<RequirePermission permission={PERM.VIEW_MODEL_QUALITY}><ModelsPage /></RequirePermission>} />
              <Route path="/data-quality" element={<RequirePermission permission={PERM.VIEW_MODEL_QUALITY}><DataQualityPage /></RequirePermission>} />

              {/* Quản trị */}
              <Route path="/sar/:sarId/edit" element={<RequirePermission permission={PERM.PREPARE_SAR}><SarEditPage /></RequirePermission>} />
              <Route path="/approvals" element={<RequirePermission permission={PERM.APPROVE_CASE}><ApprovalsPage /></RequirePermission>} />
              <Route path="/projects" element={<RequirePermission permission={PERM.VIEW_CRYPTO}><ProjectsPage /></RequirePermission>} />
              <Route path="/approvals/:sarId" element={<RequirePermission permission={PERM.APPROVE_CASE}><ApprovalDetailPage /></RequirePermission>} />
              <Route path="/audit" element={<RequirePermission permission={PERM.VIEW_AUDIT_LOG}><AuditPage /></RequirePermission>} />
              <Route path="/users" element={<RequirePermission permission={PERM.MANAGE_USERS}><UsersPage /></RequirePermission>} />
              <Route path="/settings" element={<RequirePermission permission={PERM.MANAGE_SYSTEM}><SettingsPage /></RequirePermission>} />
              <Route path="*" element={<NotFoundPage />} />
            </Route>
            <Route path="/" element={<Navigate to="/login" replace />} />
          </Routes>
        </BrowserRouter>
      </ConsoleProvider>
    </AppProvider>
  );
}
