import { LogOut, PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { NavLink, useNavigate } from "react-router-dom";

import { NAV } from "../../config/nav";
import { NAV_PERMISSION } from "../../rbac/navPermissions";
import { useRbac } from "../../rbac/useRbac";
import { transitions, useReduced } from "../../design/motion";
import { TEXT } from "../../design/typography";
import { useApp } from "../../context/AppContext";
import { useConsole } from "../../context/ConsoleContext";
import { IconButton, Tooltip } from "../ui";

interface Props {
  /** Số việc tồn đọng, khớp khoá `badge` trong `NAV`. */
  counts?: Partial<Record<"alerts" | "approvals", number>>;
  /** Ở khung hẹp, sidebar là lớp phủ và cần đóng lại sau khi điều hướng. */
  onNavigate?: () => void;
}

const EXPANDED = 218;
const COLLAPSED = 58;

export function Sidebar({ counts = {}, onNavigate }: Props) {
  const { currentUser, logout } = useApp();
  const { sidebarCollapsed: collapsed, toggleSidebar } = useConsole();
  const navigate = useNavigate();
  const reduced = useReduced();
  const rbac = useRbac();

  // Lọc theo QUYỀN (khớp route guard), không theo mảng roles cũ. Mục không có
  // trong bảng quyền thì mọi người đã đăng nhập đều thấy.
  const items = NAV.filter((it) => {
    const need = NAV_PERMISSION[it.to];
    return need ? rbac.can(need) : true;
  });

  return (
    <motion.nav
      aria-label="Điều hướng chính"
      initial={false}
      animate={{ width: collapsed ? COLLAPSED : EXPANDED }}
      transition={reduced ? { duration: 0.01 } : transitions.layout}
      className="flex h-full flex-none flex-col overflow-hidden border-r border-line bg-side"
    >
      <div className="flex flex-none items-center gap-2.5 border-b border-line-soft px-[13px] py-3">
        <div className="grid h-[30px] w-[30px] flex-none place-items-center rounded-control border border-line-strong bg-elev font-mono text-meta font-semibold text-ink-mid">
          F7
        </div>
        {/* Nhãn thương hiệu mờ dần tại chỗ thay vì bị cắt cụt theo bề rộng:
            cắt cụt làm chữ nhảy từng ký tự trong suốt quá trình thu gọn. */}
        <AnimatePresence initial={false}>
          {!collapsed && (
            <motion.div
              initial={reduced ? { opacity: 0 } : { opacity: 0, x: -6 }}
              animate={{ opacity: 1, x: 0 }}
              exit={reduced ? { opacity: 0 } : { opacity: 0, x: -6 }}
              transition={reduced ? { duration: 0.01 } : transitions.state}
              className="min-w-0 whitespace-nowrap"
            >
              <div className="truncate-1 text-body-lg font-semibold tracking-[0.02em] text-ink-hi">
                FIN-07 · Thành phố tài chính
              </div>
              <div className={TEXT.eyebrow}>Trung tâm điều hành AML</div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto overflow-x-hidden py-1.5">
        {items.map((item) => {
          const badge = item.badge ? counts[item.badge] : undefined;
          const hasBadge = badge != null && badge > 0;
          // Huy hiệu là chip nhỏ: số hàng nghìn (vd 10004 cảnh báo) sẽ tràn và
          // khó đọc. Chặn trên ở "999+" để giữ khuôn, con số đầy đủ ở trang tương ứng.
          const badgeText = badge != null && badge > 999 ? "999+" : badge;

          const link = (
            <NavLink
              to={item.to}
              onClick={onNavigate}
              className={({ isActive }) =>
                `relative mx-2 my-px flex items-center gap-2.5 rounded-control px-3 py-[7px] transition-colors ${
                  isActive ? "bg-elev font-medium text-ink-hi" : "text-ink-soft hover:bg-elev/60 hover:text-ink-mid"
                }`
              }
            >
              {({ isActive }) => (
                <>
                  {/* Một chỉ báo duy nhất trượt giữa các mục, không phải mỗi mục
                      tự bật vạch của mình: mắt bám theo được nó và biết vừa đi
                      từ đâu sang đâu. */}
                  {isActive && (
                    <motion.span
                      layoutId="sidebar-active"
                      transition={reduced ? { duration: 0.01 } : transitions.state}
                      className="absolute -left-2 bottom-1.5 top-1.5 w-0.5 rounded-sm bg-primary"
                      aria-hidden
                    />
                  )}
                  <item.icon
                    size={16}
                    strokeWidth={1.6}
                    className={`flex-none transition-colors ${isActive ? "text-primary" : ""}`}
                    aria-hidden
                  />
                  <AnimatePresence initial={false}>
                    {!collapsed && (
                      <motion.span
                        initial={reduced ? { opacity: 0 } : { opacity: 0, x: -4 }}
                        animate={{ opacity: 1, x: 0 }}
                        exit={{ opacity: 0 }}
                        transition={reduced ? { duration: 0.01 } : transitions.feedback}
                        className="truncate-1 flex-1 whitespace-nowrap text-body"
                      >
                        {item.label}
                      </motion.span>
                    )}
                  </AnimatePresence>
                  {!collapsed && hasBadge && (
                    <span className="tabular flex-none rounded-chip bg-risk/15 px-1.5 font-mono text-micro leading-[17px] text-risk-soft">
                      {badgeText}
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
          );

          return (
            <div key={item.to}>
              {item.section &&
                (collapsed ? (
                  // Thu gọn thì không còn chỗ cho nhãn nhóm — một đường kẻ vẫn
                  // giữ được ranh giới giữa các nhóm.
                  <div className="mx-3 my-2 border-t border-line-soft" />
                ) : (
                  <div className={`${TEXT.eyebrow} truncate-1 px-4 pb-1 pt-4`}>{item.section}</div>
                ))}
              {collapsed ? (
                <Tooltip label={item.label} side="right" className="block">
                  {link}
                </Tooltip>
              ) : (
                link
              )}
            </div>
          );
        })}
      </div>

      <div className="flex flex-none items-center gap-2 border-t border-line-soft px-3 py-2.5">
        <IconButton
          size="sm"
          variant="secondary"
          label={collapsed ? "Mở rộng thanh điều hướng" : "Thu gọn thanh điều hướng"}
          icon={collapsed ? <PanelLeftOpen size={14} /> : <PanelLeftClose size={14} />}
          onClick={toggleSidebar}
        />
        <AnimatePresence initial={false}>
          {!collapsed && currentUser && (
            <motion.div
              initial={reduced ? { opacity: 0 } : { opacity: 0, x: -4 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0 }}
              transition={reduced ? { duration: 0.01 } : transitions.feedback}
              className="flex min-w-0 flex-1 items-center gap-2"
            >
              <div className="min-w-0 flex-1 whitespace-nowrap text-meta text-ink-low">
                <div className="truncate-1 text-ink-soft">{currentUser.name}</div>
                <div className="truncate-1 text-micro">{currentUser.roleLabel}</div>
              </div>
              <IconButton
                size="sm"
                variant="secondary"
                label="Đăng xuất"
                icon={<LogOut size={13} />}
                onClick={() => void logout().then(() => navigate("/login", { replace: true }))}
                className="hover:border-risk/50 hover:text-risk-soft"
              />
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </motion.nav>
  );
}
