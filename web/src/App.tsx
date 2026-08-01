import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import { AccessDenied } from "./components/common/AccessDenied";
import { ToastRegion } from "./components/common/Toast";
import { AppLayout } from "./components/layout/AppLayout";
import { AppProvider } from "./context/AppContext";
import { AlertDetailPage } from "./pages/AlertDetailPage";
import { AlertsPage } from "./pages/AlertsPage";
import { ApprovalDetailPage } from "./pages/ApprovalDetailPage";
import { ApprovalsPage } from "./pages/ApprovalsPage";
import { AuditPage } from "./pages/AuditPage";
import { CaseDetailPage } from "./pages/CaseDetailPage";
import { CasesPage } from "./pages/CasesPage";
import { DashboardPage } from "./pages/DashboardPage";
import { LoginPage } from "./pages/LoginPage";
import { NetworkPage } from "./pages/NetworkPage";
import { SarEditPage } from "./pages/SarEditPage";
import { SettingsPage } from "./pages/SettingsPage";
import { UsersPage } from "./pages/UsersPage";

export default function App() {
  return (
    <AppProvider>
      <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <Routes>
          <Route path="/login" element={<><LoginPage /><ToastRegion /></>} />
          <Route path="/403" element={<><AccessDenied /><ToastRegion /></>} />
          <Route element={<AppLayout />}>
            <Route path="/dashboard" element={<DashboardPage />} />
            <Route path="/alerts" element={<AlertsPage />} />
            <Route path="/alerts/:alertId" element={<AlertDetailPage />} />
            <Route path="/cases" element={<CasesPage />} />
            <Route path="/cases/:caseId" element={<CaseDetailPage />} />
            <Route path="/network/:caseId" element={<NetworkPage />} />
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
    </AppProvider>
  );
}
