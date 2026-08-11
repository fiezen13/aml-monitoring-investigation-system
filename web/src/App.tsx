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
import { CryptoPage } from "./pages/CryptoPage";
import { DashboardPage } from "./pages/DashboardPage";
import { DataQualityPage } from "./pages/DataQualityPage";
import { EntityNetworkPage } from "./pages/EntityNetworkPage";
import { LoginPage } from "./pages/LoginPage";
import { ModelsPage } from "./pages/ModelsPage";
import { NetworkPage } from "./pages/NetworkPage";
import { ProjectsPage } from "./pages/ProjectsPage";
import { SarEditPage } from "./pages/SarEditPage";
import { SettingsPage } from "./pages/SettingsPage";
import { TransactionsPage } from "./pages/TransactionsPage";
import { UsersPage } from "./pages/UsersPage";
import { WorldPage } from "./pages/WorldPage";

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
              <Route path="/world" element={<WorldPage />} />

              {/* Điều tra */}
              <Route path="/alerts" element={<AlertsPage />} />
              <Route path="/alerts/:alertId" element={<AlertDetailPage />} />
              <Route path="/cases" element={<CasesPage />} />
              <Route path="/cases/:caseId" element={<CaseDetailPage />} />
              {/* Hai đồ thị khác nhau có chủ đích: `/network` là toàn bộ mạng
                  lưới mô phỏng, `/network/:caseId` là đồ thị gọn của một vụ việc. */}
              <Route path="/network" element={<EntityNetworkPage />} />
              <Route path="/network/:caseId" element={<NetworkPage />} />
              <Route path="/transactions" element={<TransactionsPage />} />

              {/* Tài sản mã hoá */}
              <Route path="/crypto" element={<CryptoPage />} />
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
            </Route>
            <Route path="/" element={<Navigate to="/login" replace />} />
            <Route path="*" element={<Navigate to="/login" replace />} />
          </Routes>
        </BrowserRouter>
      </ConsoleProvider>
    </AppProvider>
  );
}
