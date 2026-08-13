import { LogOut, PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { NavLink, useNavigate } from "react-router-dom";

import { NAV } from "../../config/nav";
import { useApp } from "../../context/AppContext";
import { useConsole } from "../../context/ConsoleContext";

interface Props {
  /** Số việc tồn đọng, khớp khoá `badge` trong `NAV`. */
  counts?: Partial<Record<"alerts" | "approvals", number>>;
}

export function Sidebar({ counts = {} }: Props) {
  const { currentUser, logout } = useApp();
  const { sidebarCollapsed: collapsed, toggleSidebar } = useConsole();
  const navigate = useNavigate();

  const items = NAV.filter((it) => !it.roles || (currentUser && it.roles.includes(currentUser.role)));

  return (
    <nav
      aria-label="Điều hướng chính"
      className="flex flex-none flex-col border-r border-line bg-side transition-[width] duration-200"
      style={{ width: collapsed ? 58 : 218 }}
    >
      <div className="flex items-center gap-2.5 border-b border-line-soft px-4 py-3.5">
        <div className="grid h-[30px] w-[30px] flex-none place-items-center rounded-[9px] border border-primary-line bg-gradient-to-br from-[#0E3A44] to-[#0A1F33] font-mono text-2xs font-semibold text-primary">
          F7
        </div>
        {!collapsed && (
          <div className="min-w-0">
            <div className="truncate-1 text-lg font-semibold tracking-[0.02em]">FIN-07 · Thành phố tài chính</div>
            <div className="text-3xs uppercase tracking-[0.14em] text-ink-low">Trung tâm điều hành AML</div>
          </div>
        )}
      </div>

      <div className="flex-1 overflow-y-auto overflow-x-hidden py-1.5">
        {items.map((it) => {
          const badge = it.badge ? counts[it.badge] : undefined;
          const hasBadge = badge != null && badge > 0;
          return (
            <div key={it.to}>
              {it.section &&
                (collapsed ? (
                  // Thu gọn thì không còn chỗ cho nhãn nhóm — một đường kẻ vẫn
                  // giữ được ranh giới giữa các nhóm.
                  <div className="mx-3 my-2 border-t border-line-soft" />
                ) : (
                  <div className="px-[18px] pb-1 pt-3.5 text-3xs uppercase tracking-[0.14em] text-ink-dim">
                    {it.section}
                  </div>
                ))}
              <NavLink
                to={it.to}
                title={it.label}
                className={({ isActive }) =>
                  `relative mx-2 my-px flex items-center gap-2.5 rounded-control px-3 py-1.5 transition-colors ${
                    isActive ? "bg-primary-soft text-ink-hi" : "text-ink-soft hover:bg-elev hover:text-ink-hi"
                  }`
                }
              >
                {({ isActive }) => (
                  <>
                    {isActive && (
                      <span className="absolute -left-2 bottom-[7px] top-[7px] w-[3px] rounded-sm bg-primary" />
                    )}
                    <it.icon size={16} strokeWidth={1.7} className="flex-none" aria-hidden />
                    {!collapsed && <span className="truncate-1 flex-1 text-base">{it.label}</span>}
                    {!collapsed && hasBadge && (
                      <span className="tabular flex-none rounded-chip border border-risk/30 bg-risk/15 px-1.5 font-mono text-2xs leading-4 text-risk-soft">
                        {badge}
                      </span>
                    )}
                    {/* Ở dạng thu gọn con số không đọc nổi, nhưng "đang có việc
                        tồn" thì vẫn phải thấy — rút xuống còn một chấm. */}
                    {collapsed && hasBadge && (
                      <span
                        className="absolute right-1.5 top-1.5 h-1.5 w-1.5 rounded-full bg-risk"
                        aria-label={`${badge} mục cần xử lý`}
                      />
                    )}
                  </>
                )}
              </NavLink>
            </div>
          );
        })}
      </div>

      <div className="flex items-center gap-2 border-t border-line-soft px-3 py-2.5">
        <button
          type="button"
          onClick={toggleSidebar}
          aria-label={collapsed ? "Mở rộng sidebar" : "Thu gọn sidebar"}
          className="grid h-7 w-7 flex-none place-items-center rounded-[7px] border border-line-strong/70 text-ink-soft transition-colors hover:border-line-strong hover:text-ink-hi"
        >
          {collapsed ? <PanelLeftOpen size={14} /> : <PanelLeftClose size={14} />}
        </button>
        {!collapsed && currentUser && (
          <>
            <div className="min-w-0 flex-1 text-2xs text-ink-low">
              <div className="truncate-1 text-ink-soft">{currentUser.name}</div>
              <div className="truncate-1 text-3xs">{currentUser.roleLabel}</div>
            </div>
            <button
              type="button"
              onClick={() => void logout().then(() => navigate("/login", { replace: true }))}
              aria-label="Đăng xuất"
              title="Đăng xuất"
              className="grid h-7 w-7 flex-none place-items-center rounded-[7px] border border-line-strong/70 text-ink-soft transition-colors hover:border-risk/50 hover:text-risk-soft"
            >
              <LogOut size={13} />
            </button>
          </>
        )}
      </div>
    </nav>
  );
}
