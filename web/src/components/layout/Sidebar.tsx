import {
  Bell,
  ClipboardCheck,
  FileCheck2,
  History,
  LayoutGrid,
  LogOut,
  Settings,
  Shield,
  Users,
} from "lucide-react";
import { NavLink, useNavigate } from "react-router-dom";

import { useApp } from "../../context/AppContext";

const NAV_ITEMS = [
  { to: "/dashboard", label: "Tổng quan", icon: LayoutGrid },
  { to: "/alerts", label: "Cảnh báo", icon: Bell, badge: 18 },
  { to: "/cases", label: "Vụ việc", icon: ClipboardCheck },
  { to: "/approvals", label: "Phê duyệt SAR", icon: FileCheck2 },
  { to: "/audit", label: "Audit trail", icon: History },
  { to: "/users", label: "Người dùng", icon: Users },
  { to: "/settings", label: "Cấu hình", icon: Settings },
];

export function Sidebar() {
  const { currentUser, logout } = useApp();
  const navigate = useNavigate();

  return (
    <aside className="flex h-full w-[210px] shrink-0 flex-col border-r border-line bg-side">
      {/* Logo */}
      <div className="flex items-center gap-2.5 px-4 py-4">
        <span className="flex h-8 w-8 items-center justify-center rounded-control bg-primary/20 text-primary">
          <Shield size={17} aria-hidden />
        </span>
        <div>
          <div className="text-[15px] font-bold leading-tight text-ink-hi">Velrix</div>
          <div className="text-2xs font-semibold uppercase tracking-[0.18em] text-ink-low">
            AML Console
          </div>
        </div>
      </div>

      {/* Điều hướng */}
      <nav className="mt-2 flex-1 space-y-0.5 px-2.5" aria-label="Điều hướng chính">
        {NAV_ITEMS.map(({ to, label, icon: Icon, badge }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              `flex items-center gap-2.5 rounded-control border-l-2 px-2.5 py-2 text-[13px] font-medium transition-colors ${
                isActive
                  ? "border-primary bg-primary-soft text-ink-hi"
                  : "border-transparent text-ink-mid hover:bg-panel hover:text-ink-hi"
              }`
            }
          >
            <Icon size={15} aria-hidden />
            <span className="flex-1">{label}</span>
            {badge !== undefined && (
              <span className="tabular rounded-full bg-risk px-1.5 py-px text-2xs font-bold text-white">
                {badge}
              </span>
            )}
          </NavLink>
        ))}
      </nav>

      {/* Trạng thái hệ thống + người dùng + đăng xuất */}
      <div className="space-y-2.5 px-3 pb-4">
        <div className="rounded-panel border border-primary/25 bg-primary-soft p-2.5">
          <div className="flex items-center gap-1.5 text-2xs font-semibold text-primary">
            <span className="h-1.5 w-1.5 rounded-full bg-ok" aria-hidden />
            AI Copilot Online
          </div>
          <p className="mt-1 text-2xs leading-snug text-ink-mid">
            Hệ thống đang giám sát 24/7. Sẵn sàng phân tích hàng đợi của bạn.
          </p>
        </div>

        {currentUser && (
          <div className="flex items-center gap-2 rounded-panel border border-line bg-panel p-2">
            <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-elev text-2xs font-bold text-primary">
              {currentUser.name
                .split(" ")
                .slice(-2)
                .map((w) => w[0])
                .join("")}
            </span>
            <div className="min-w-0 flex-1">
              <div className="truncate text-2xs font-semibold text-ink-hi">
                {currentUser.name}
              </div>
              <div className="truncate text-2xs text-ink-low">{currentUser.roleLabel}</div>
            </div>
            <button
              type="button"
              title="Đăng xuất"
              aria-label="Đăng xuất"
              onClick={() => {
                logout();
                navigate("/login");
              }}
              className="shrink-0 rounded p-1 text-ink-low hover:bg-elev hover:text-risk"
            >
              <LogOut size={13} />
            </button>
          </div>
        )}

        <button
          type="button"
          className="flex w-full items-center gap-2 px-1 text-2xs text-ink-low hover:text-ink-hi"
        >
          <span className="flex h-4 w-4 items-center justify-center rounded-full border border-line text-[9px]">
            ?
          </span>
          Hỗ trợ hệ thống
        </button>
      </div>
    </aside>
  );
}
