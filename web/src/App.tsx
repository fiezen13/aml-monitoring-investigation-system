import { Suspense, lazy } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import { AccessDenied } from "./components/common/AccessDenied";
import { ToastRegion } from "./components/common/Toast";
import { AppLayout } from "./components/layout/AppLayout";
import { AppProvider } from "./context/AppContext";
import { ConsoleProvider } from "./context/ConsoleContext";
import { AgentRunPage, AgentsPage } from "./pages/AgentsPage";
import { AlertDetailPage } from "./pages/AlertDetailPage";
import { AlertsPage } from "./pages/AlertsPage";
import { ApprovalDetailPage } from "./pages/ApprovalDetailPage";
import { ApprovalsPage } from "./pages/ApprovalsPage";
import { AuditPage } from "./pages/AuditPage";
import { BenchmarksPage } from "./pages/BenchmarksPage";
import { CaseDetailPage } from "./pages/CaseDetailPage";
import { CasesPage } from "./pages/CasesPage";
import { DashboardPage } from "./pages/DashboardPage";
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
const EntityNetworkPage = lazy(() =>
  import("./pages/EntityNetworkPage").then((m) => ({ default: m.EntityNetworkPage })),
);
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
              <Route path="/dashboard" element={<DashboardPage />} />
              <Route
                path="/world"
                element={
                  <HeavyRoute label="Đang nạp bộ dựng bản đồ…">
                    <WorldPage />
                  </HeavyRoute>
                }
              />

              {/* Điều tra */}
              <Route path="/alerts" element={<AlertsPage />} />
              <Route path="/alerts/:alertId" element={<AlertDetailPage />} />
              <Route path="/cases" element={<CasesPage />} />
              <Route path="/cases/:caseId" element={<CaseDetailPage />} />
              {/* Hai đồ thị khác nhau có chủ đích: `/network` là toàn bộ mạng
                  lưới mô phỏng, `/network/:caseId` là đồ thị gọn của một vụ việc. */}
              <Route
                path="/network"
                element={
                  <HeavyRoute label="Đang nạp bộ dựng đồ thị…">
                    <EntityNetworkPage />
                  </HeavyRoute>
                }
              />
              <Route
                path="/network/:caseId"
                element={
                  <HeavyRoute label="Đang nạp bộ dựng đồ thị…">
                    <NetworkPage />
                  </HeavyRoute>
                }
              />
              <Route path="/transactions" element={<TransactionsPage />} />

              {/* Tài sản mã hoá */}
              <Route
                path="/crypto"
                element={
                  <HeavyRoute label="Đang nạp màn truy vết…">
                    <CryptoPage />
                  </HeavyRoute>
                }
              />
              <Route path="/projects" element={<ProjectsPage />} />

              {/* AI Agent */}
              <Route path="/agents" element={<AgentsPage />} />
              <Route path="/agents/:runId" element={<AgentRunPage />} />

              {/* Chất lượng và mô hình */}
              <Route path="/benchmarks" element={<BenchmarksPage />} />
              <Route path="/models" element={<ModelsPage />} />
              <Route path="/data-quality" element={<DataQualityPage />} />

              {/* Quản trị */}
              <Route path="/sar/:sarId/edit" element={<SarEditPage />} />
              <Route path="/approvals" element={<ApprovalsPage />} />
              <Route path="/approvals/:sarId" element={<ApprovalDetailPage />} />
              <Route path="/audit" element={<AuditPage />} />
              <Route path="/users" element={<UsersPage />} />
              <Route path="/settings" element={<SettingsPage />} />
              <Route path="*" element={<NotFoundPage />} />
            </Route>
            <Route path="/" element={<Navigate to="/login" replace />} />
          </Routes>
        </BrowserRouter>
      </ConsoleProvider>
    </AppProvider>
  );
}
